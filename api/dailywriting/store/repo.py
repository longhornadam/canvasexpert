"""Record storage for the daily writing substrate.

Atomic JSON documents with an interprocess lock, following
`api/operation_ledger`. No SQLite: nothing else in this repository uses one,
and a second persistence stack with a single consumer is a cost with no payer.

Documents are partitioned by month (`submissions/2026-09.json` and siblings),
which keeps each file small and matches how the data is actually read: a
four-week profile window touches one or two files.

`Submission`, `Score`, `Observation`, and `DirectiveEval` are append-only. Runs
are idempotent anyway, because readers keep the last entry for a given id and
ids are derived rather than generated. That combination is deliberate: a
re-ingest after a fixed segmentation bug leaves the earlier attempt in the
record for anyone auditing what the system used to think, without letting it
steer anything today.

`RollingProfile` is derived and replaceable, never the source of truth. Deleting
every profile file costs one regeneration and no information.

Everything on disk is keyed by Canvas user id and lives in the workspace's
PRIVATE `_System` tier. Pseudonyms are what leave this module.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from api.dailywriting.core.models import (
    Directive,
    Observation,
    RollingProfile,
    Score,
    Submission,
)
from api.dailywriting.core.scrub import assert_clean_for_storage
from api.dailywriting.store import codec
from api.dailywriting.store.identity import IdentityResolver, VaultResolver
from api.storage_support import atomic_write_json, interprocess_lock

STORE_FOLDER = "Daily Writing"

SUBMISSIONS = "submissions"
SCORES = "scores"
OBSERVATIONS = "observations"


class StoreError(RuntimeError):
    """The store cannot be located or a document cannot be read."""


def workspace_store_root() -> Path:
    """`_System/Daily Writing` inside the synced workspace.

    `_System` is the PRIVATE machine-state tier, which is where PowerGrader's
    sessions and the identity vault already live. Raises when there is no
    workspace, rather than inventing a location that would not be backed up.
    """
    from api.webui import workspace

    folder = workspace.system_folder(STORE_FOLDER)
    if not folder:
        raise StoreError(
            "no Canvas Expert workspace is configured, so there is nowhere "
            "private to keep daily writing records"
        )
    return Path(folder)


class Repository:
    """Append-only record store for one teacher's daily writing practice."""

    def __init__(self, root: Path | str, *, resolver: IdentityResolver,
                 vault=None):
        self.root = Path(root)
        self.resolver = resolver
        self.vault = vault

    @classmethod
    def default(cls) -> Repository:
        from api.powergrader import context

        vault = context.vault()
        return cls(workspace_store_root(), resolver=VaultResolver(vault),
                   vault=vault)

    # --- plumbing ---------------------------------------------------------

    def _path(self, kind: str, partition: str) -> Path:
        return self.root / kind / f"{partition}.json"

    def _single(self, name: str) -> Path:
        return self.root / f"{name}.json"

    @staticmethod
    def _partition(when: datetime | date) -> str:
        return f"{when.year:04d}-{when.month:02d}"

    def _read(self, path: Path, key: str) -> list[dict]:
        if not path.exists():
            return []
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StoreError(f"{path} is not valid JSON: {exc}") from exc
        entries = document.get(key, [])
        if not isinstance(entries, list):
            raise StoreError(f"{path} has a malformed {key!r} list")
        return entries

    def _append(self, path: Path, key: str, records: list[dict]) -> None:
        if not records:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with interprocess_lock(path.with_suffix(".lock")):
            existing = self._read(path, key)
            existing.extend(records)
            atomic_write_json(path, {"schema": codec.DOCUMENT_VERSION,
                                     key: existing})

    @staticmethod
    def _latest_by(entries: list[dict], id_key: str) -> list[dict]:
        """Last entry wins for a repeated id, preserving first-seen order."""
        order: list[str] = []
        latest: dict[str, dict] = {}
        for entry in entries:
            identifier = entry.get(id_key)
            if identifier not in latest:
                order.append(identifier)
            latest[identifier] = entry
        return [latest[identifier] for identifier in order]

    def _partitions(self, kind: str) -> list[Path]:
        folder = self.root / kind
        if not folder.exists():
            return []
        return sorted(folder.glob("*.json"))

    def _months_between(self, start: date, end: date) -> list[str]:
        months: list[str] = []
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            months.append(f"{year:04d}-{month:02d}")
            month += 1
            if month > 12:
                year, month = year + 1, 1
        return months

    # --- writes -----------------------------------------------------------

    def append_submission(self, submission: Submission) -> None:
        """Store one submission. Text must already be scrubbed."""
        assert_clean_for_storage(submission.raw_text, self.vault)
        canvas_id = self.resolver.to_canvas_id(submission.pseudonym_id)
        self._append(
            self._path(SUBMISSIONS, self._partition(submission.submitted_at)),
            "submissions",
            [codec.submission_to_dict(submission, canvas_id=canvas_id)],
        )

    def append_score(self, score: Score, pseudonym_id: str) -> None:
        for result in score.per_item.values():
            if result.evidence_span:
                assert_clean_for_storage(result.evidence_span.text, self.vault)
        canvas_id = self.resolver.to_canvas_id(pseudonym_id)
        self._append(
            self._path(SCORES, self._partition(score.scored_at)), "scores",
            [codec.score_to_dict(score, canvas_id=canvas_id)],
        )

    def append_observations(self, observations: list[Observation]) -> None:
        by_partition: dict[str, list[dict]] = {}
        for observation in observations:
            assert_clean_for_storage(observation.evidence_span, self.vault)
            canvas_id = self.resolver.to_canvas_id(observation.pseudonym_id)
            partition = self._partition(observation.observed_at)
            by_partition.setdefault(partition, []).append(
                codec.observation_to_dict(observation, canvas_id=canvas_id))
        for partition, records in by_partition.items():
            self._append(self._path(OBSERVATIONS, partition), "observations",
                         records)

    def put_directive(self, directive: Directive) -> None:
        """Replace one directive in place.

        A directive's status and streaks are mutable state, unlike the
        evaluations it carries, which only ever grow.
        """
        canvas_id = self.resolver.to_canvas_id(directive.pseudonym_id)
        path = self._single("directives")
        path.parent.mkdir(parents=True, exist_ok=True)
        with interprocess_lock(path.with_suffix(".lock")):
            entries = self._read(path, "directives")
            record = codec.directive_to_dict(directive, canvas_id=canvas_id)
            replaced = False
            for index, entry in enumerate(entries):
                if entry.get("directive_id") == directive.directive_id:
                    entries[index] = record
                    replaced = True
                    break
            if not replaced:
                entries.append(record)
            atomic_write_json(path, {"schema": codec.DOCUMENT_VERSION,
                                     "directives": entries})

    def set_tier(self, pseudonym_id: str, tier: int) -> None:
        """Record a student's current tier. Only a teacher calls this path."""
        canvas_id = self.resolver.to_canvas_id(pseudonym_id)
        path = self._single("tiers")
        path.parent.mkdir(parents=True, exist_ok=True)
        with interprocess_lock(path.with_suffix(".lock")):
            document = {}
            if path.exists():
                document = json.loads(path.read_text(encoding="utf-8"))
            tiers = document.get("tiers", {})
            tiers[str(canvas_id)] = int(tier)
            atomic_write_json(path, {"schema": codec.DOCUMENT_VERSION,
                                     "tiers": tiers})

    def put_profile(self, profile: RollingProfile) -> None:
        canvas_id = self.resolver.to_canvas_id(profile.pseudonym_id)
        path = self.root / "profiles" / f"{canvas_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with interprocess_lock(path.with_suffix(".lock")):
            atomic_write_json(path, codec.profile_to_dict(
                profile, canvas_id=canvas_id))

    # --- reads ------------------------------------------------------------

    def read_profile(self, pseudonym_id: str) -> RollingProfile | None:
        """Read a stored profile.

        Exists for the feedback and digest paths. `core.profile` must never
        call it: INV-4 says a regeneration re-derives from the record, and a
        regeneration that read the last profile would launder September's
        label into November.
        """
        canvas_id = self.resolver.to_canvas_id(pseudonym_id)
        path = self.root / "profiles" / f"{canvas_id}.json"
        if not path.exists():
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
        return codec.profile_from_dict(document, pseudonym_id=pseudonym_id)

    def submissions_in_window(self, pseudonym_id: str, start: date,
                              end: date) -> list[Submission]:
        canvas_id = self.resolver.to_canvas_id(pseudonym_id)
        found: list[dict] = []
        for partition in self._months_between(start, end):
            found.extend(self._read(self._path(SUBMISSIONS, partition),
                                    "submissions"))
        results = [
            codec.submission_from_dict(entry, pseudonym_id=pseudonym_id)
            for entry in self._latest_by(found, "submission_id")
            if str(entry.get("canvas_id")) == str(canvas_id)
        ]
        return sorted(
            [s for s in results if start <= s.submitted_at.date() <= end],
            key=lambda s: s.submitted_at)

    def section_submissions(self, pseudonym_ids: list[str], start: date,
                            end: date) -> list[Submission]:
        """Every submission from a set of students in a window."""
        results: list[Submission] = []
        for pseudonym_id in pseudonym_ids:
            results.extend(self.submissions_in_window(pseudonym_id, start, end))
        return sorted(results, key=lambda s: s.submitted_at)

    def scores_for(self, submission_ids: list[str]) -> dict[str, Score]:
        """Scores for a set of submissions.

        Scans every month partition, because a score's month is the month it
        was scored and need not match the month the work came in. The file
        count is one per month of practice, so the scan stays cheap.
        """
        wanted = set(submission_ids)
        if not wanted:
            return {}
        found: list[dict] = []
        for path in self._partitions(SCORES):
            found.extend(entry for entry in self._read(path, "scores")
                         if entry.get("submission_id") in wanted)
        return {entry["submission_id"]: codec.score_from_dict(entry)
                for entry in self._latest_by(found, "submission_id")}

    def observations_in_window(self, pseudonym_id: str, start: date,
                               end: date) -> list[Observation]:
        canvas_id = self.resolver.to_canvas_id(pseudonym_id)
        found: list[dict] = []
        for partition in self._months_between(start, end):
            found.extend(self._read(self._path(OBSERVATIONS, partition),
                                    "observations"))
        results = [
            codec.observation_from_dict(entry, pseudonym_id=pseudonym_id)
            for entry in self._latest_by(found, "obs_id")
            if str(entry.get("canvas_id")) == str(canvas_id)
        ]
        return sorted(
            [o for o in results if start <= o.observed_at.date() <= end],
            key=lambda o: o.observed_at)

    def section_observations(self, pseudonym_ids: list[str], start: date,
                             end: date) -> list[Observation]:
        results: list[Observation] = []
        for pseudonym_id in pseudonym_ids:
            results.extend(self.observations_in_window(pseudonym_id, start, end))
        return sorted(results, key=lambda o: o.observed_at)

    def directives_for(self, pseudonym_id: str) -> list[Directive]:
        canvas_id = self.resolver.to_canvas_id(pseudonym_id)
        entries = self._read(self._single("directives"), "directives")
        return [codec.directive_from_dict(entry, pseudonym_id=pseudonym_id)
                for entry in entries
                if str(entry.get("canvas_id")) == str(canvas_id)]

    def current_tier(self, pseudonym_id: str) -> int:
        """The student's tier. Tier is per student, not global: sections
        advance on different dates and students inside them do too."""
        canvas_id = self.resolver.to_canvas_id(pseudonym_id)
        path = self._single("tiers")
        if not path.exists():
            return 1
        document = json.loads(path.read_text(encoding="utf-8"))
        return int(document.get("tiers", {}).get(str(canvas_id), 1))

    def weekly_totals(self, pseudonym_id: str, start: date,
                      end: date) -> dict:
        """Daily results plus a weekly aggregate for one student.

        Exposed so either gradebook presentation stays possible (one weekly
        column, or a filtered assignment group) without this package choosing
        between them. It writes nothing to Canvas.
        """
        submissions = self.submissions_in_window(pseudonym_id, start, end)
        scores = self.scores_for([s.submission_id for s in submissions])
        daily = []
        earned = possible = 0
        for submission in submissions:
            score = scores.get(submission.submission_id)
            if score is None:
                continue
            daily.append({
                "rep_id": submission.rep_id,
                "on": submission.submitted_at.date().isoformat(),
                "total": score.total,
                "possible": score.possible,
                "status": score.status,
            })
            if score.status == "scored":
                earned += score.total
                possible += score.possible
        return {
            "pseudonym_id": pseudonym_id,
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "daily": daily,
            "reps_submitted": len(daily),
            "earned": earned,
            "possible": possible,
        }
