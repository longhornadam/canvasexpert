"""Private, append-only evidence store for Writing Record."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from api.dailywriting.config import naming
from api.dailywriting.core.models import AssignmentContext, Submission
from api.dailywriting.core.scrub import assert_clean_for_storage
from api.dailywriting.store import codec
from api.dailywriting.store.identity import IdentityResolver, VaultResolver
from api.storage_support import atomic_write_json, interprocess_lock

STORE_FOLDER = naming.SYSTEM_NAME
SUBMISSIONS = "submissions"


class StoreError(RuntimeError):
    """The private Writing Record store cannot be located or read."""


def workspace_store_root() -> Path:
    from api.platform_services import workspace
    folder = workspace.system_folder(STORE_FOLDER)
    if not folder:
        raise StoreError("no Canvas Expert workspace is configured, so there is nowhere private to keep writing records")
    return Path(folder)


class Repository:
    """One source of truth for assignment context and one for submissions."""
    def __init__(self, root: Path | str, *, resolver: IdentityResolver, vault=None):
        self.root, self.resolver, self.vault = Path(root), resolver, vault

    @classmethod
    def default(cls) -> "Repository":
        from api.powergrader import context
        vault = context.vault()
        return cls(workspace_store_root(), resolver=VaultResolver(vault), vault=vault)

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

    def _append(self, path: Path, key: str, record: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with interprocess_lock(path.with_suffix(".lock")):
            entries = self._read(path, key)
            entries.append(record)
            atomic_write_json(path, {"schema": codec.DOCUMENT_VERSION, key: entries})

    @staticmethod
    def _latest_by(entries: list[dict], id_key: str) -> list[dict]:
        order, latest = [], {}
        for entry in entries:
            identifier = entry.get(id_key)
            if identifier not in latest:
                order.append(identifier)
            latest[identifier] = entry
        return [latest[identifier] for identifier in order]

    def _months_between(self, start: date, end: date) -> list[str]:
        months, year, month = [], start.year, start.month
        while (year, month) <= (end.year, end.month):
            months.append(f"{year:04d}-{month:02d}")
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        return months

    def append_submission(self, submission: Submission) -> None:
        assert_clean_for_storage(submission.raw_text, self.vault)
        canvas_id = self.resolver.to_canvas_id(submission.pseudonym_id)
        self._append(self._path(SUBMISSIONS, self._partition(submission.submitted_at)), "submissions", codec.submission_to_dict(submission, canvas_id=canvas_id))

    def put_rep(self, context: AssignmentContext) -> None:
        path = self._single("reps")
        path.parent.mkdir(parents=True, exist_ok=True)
        with interprocess_lock(path.with_suffix(".lock")):
            entries = self._read(path, "reps")
            record = codec.rep_to_dict(context)
            for index, entry in enumerate(entries):
                if entry.get("rep_id") == context.rep_id:
                    entries[index] = record
                    break
            else:
                entries.append(record)
            atomic_write_json(path, {"schema": codec.DOCUMENT_VERSION, "reps": entries})

    def read_rep(self, rep_id: str) -> AssignmentContext | None:
        for entry in self._read(self._single("reps"), "reps"):
            if entry.get("rep_id") == rep_id:
                return codec.rep_from_dict(entry)
        return None

    def submissions_in_window(self, pseudonym_id: str, start: date, end: date) -> list[Submission]:
        canvas_id = self.resolver.to_canvas_id(pseudonym_id)
        entries: list[dict] = []
        for partition in self._months_between(start, end):
            entries.extend(self._read(self._path(SUBMISSIONS, partition), "submissions"))
        records = [codec.submission_from_dict(entry, pseudonym_id=pseudonym_id) for entry in self._latest_by(entries, "submission_id") if str(entry.get("canvas_id")) == str(canvas_id)]
        return sorted((record for record in records if start <= record.submitted_at.date() <= end), key=lambda record: record.submitted_at)
