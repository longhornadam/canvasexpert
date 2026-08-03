"""Rename-safety for stored writing evidence: rewriting a retired pseudonym
to the student's new one across every stored span.

`api/dailywriting/core/scrub.py` stores the vault's pseudonym directly in a
stored span, deliberately -- this product measured and rejected redacting a
name out of student writing (see that module's own docstring, and
`test_dw_scrub.py::test_no_redaction_placeholder_reaches_stored_text`, the
regression guard on that decision). A rename therefore does not erase
anything on its own: it mints a new current pseudonym for one vault entry
while every already-stored span -- including a span in ANOTHER student's
writing that happens to name the renamed student as a classmate -- keeps
the OLD one baked into its text. `api.dailywriting.cli.rewrite_pseudonym`
is the fix: called once, right after a rename, it rewrites the old
pseudonym to the new one everywhere it landed.

Every name below is invented for this test file, same convention as
`api/dailywriting/fixtures/loader.py`.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from api.dailywriting.cli import rewrite_pseudonym as rewrite_module
from api.dailywriting.core import ingest, scrub
from api.dailywriting.core.models import AssignmentContext
from api.dailywriting.store.identity import MappingResolver
from api.dailywriting.store.repo import Repository

_REP_ID = "rep_rename_demo"


def _context() -> AssignmentContext:
    return AssignmentContext(
        rep_id=_REP_ID, date=date(2026, 9, 1),
        prompt_text="Write one paragraph about a favorite hobby.")


def _vault_entry(*, canvas_id: str, real_name: str, pseudonym: str) -> dict:
    first, last = pseudonym.split()
    return {
        "canvas_id": canvas_id, "sis_id": f"SIS-{canvas_id}",
        "real_name": real_name, "pseudonym": pseudonym,
        "pseudo_first": first, "pseudo_last": last, "nicknames": [],
    }


class _FixtureVault:
    """Minimal vault double: only `.entries()`, which is all
    `scrub.build_roster_map` needs for the ingest step in these tests."""

    def __init__(self, entries: list[dict]):
        self._entries = list(entries)

    def entries(self) -> list[dict]:
        return list(self._entries)


def _resolver(entries: list[dict]) -> MappingResolver:
    return MappingResolver({e["canvas_id"]: e["pseudonym"] for e in entries})


# --- the original defect, end to end -----------------------------------------

def test_original_defect_a_rename_leaves_no_stale_token_after_rewrite(tmp_path):
    """The exact scenario this batch exists to fix: ingest two students, one
    (Alex) named as a classmate inside the OTHER's (Bailey's) submission,
    then rename Alex (the compromised-pseudonym case is exactly why a
    rename happens) and rewrite. Afterward neither student's stored span,
    nor the outbound payload built from it, carries the retired pseudonym
    or any real name."""
    alex = _vault_entry(canvas_id="800001", real_name="Alex Fenwick", pseudonym="Marigold Vex")
    bailey = _vault_entry(canvas_id="800002", real_name="Bailey Kwan", pseudonym="Thistle Crane")
    roster_map = scrub.build_roster_map(_FixtureVault([alex, bailey]))

    alex_submission = ingest.ingest(
        submission_id="sub-alex-1", rep_id=_REP_ID, pseudonym_id="Marigold Vex",
        submitted_at=datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc),
        text="Alex Fenwick wrote about hiking with the family dog.",
        context=_context(), roster_map=roster_map)
    bailey_submission = ingest.ingest(
        submission_id="sub-bailey-1", rep_id=_REP_ID, pseudonym_id="Thistle Crane",
        submitted_at=datetime(2026, 9, 14, 9, 5, tzinfo=timezone.utc),
        text="My friend Alex Fenwick helped me study for the science test.",
        context=_context(), roster_map=roster_map)

    # Storage holds the pseudonym directly -- the deliberate, unchanged
    # design -- so the classmate mention already reads as a name, not a
    # redaction hole.
    assert "Marigold Vex" in alex_submission.raw_text
    assert "Marigold Vex" in bailey_submission.raw_text

    repository = Repository(tmp_path / "store", resolver=_resolver([alex, bailey]), vault=None)
    repository.put_rep(_context())
    repository.append_submission(alex_submission)
    repository.append_submission(bailey_submission)

    # The rename: Alex's canvas_id keeps its identity, the vault mints a
    # fresh current pseudonym for it. Modeled as re-opening the same on-disk
    # store with a resolver reflecting the vault AFTER the rename (a real
    # `VaultResolver` reads the live, mutated vault; `MappingResolver` is a
    # static snapshot standing in for it here).
    alex_after = _vault_entry(canvas_id="800001", real_name="Alex Fenwick", pseudonym="Juniper Weld")
    after_entries = [alex_after, bailey]
    resolver_after = _resolver(after_entries)
    repository_after = Repository(tmp_path / "store", resolver=resolver_after, vault=None)

    report = rewrite_module.rewrite_pseudonym(
        repository_after, old_pseudonym="Marigold Vex", new_pseudonym="Juniper Weld")
    assert report.submissions_changed == 2  # both spans carried the old pseudonym

    stored_alex = repository_after.submissions_in_window(
        "Juniper Weld", date(2026, 1, 1), date(2026, 12, 31))[0]
    stored_bailey = repository_after.submissions_in_window(
        "Thistle Crane", date(2026, 1, 1), date(2026, 12, 31))[0]

    # Alex's own span.
    assert "Marigold Vex" not in stored_alex.raw_text
    assert "Juniper Weld" in stored_alex.raw_text

    # The classmate mention inside Bailey's span -- the case a placeholder
    # approach could not get right, because it does not track which student
    # a mention refers to. A direct rewrite does not have that limitation.
    assert "Marigold Vex" not in stored_bailey.raw_text
    assert "Juniper Weld" in stored_bailey.raw_text
    # Bailey's own pseudonym is untouched by a rewrite that named Alex.
    assert stored_bailey.pseudonym_id == "Thistle Crane"

    # Outbound: handed the CURRENT roster's pseudonyms, exactly what
    # model_ready_text always receives. No stale token, no real name.
    current_pseudonyms = {"Juniper Weld", "Thistle Crane"}
    outbound_alex = scrub.model_ready_text(
        scrub.ScrubResult(text=stored_alex.raw_text, findings=stored_alex.scrub_findings),
        pseudonyms=current_pseudonyms, vault=None)
    outbound_bailey = scrub.model_ready_text(
        scrub.ScrubResult(text=stored_bailey.raw_text, findings=stored_bailey.scrub_findings),
        pseudonyms=current_pseudonyms, vault=None)
    for outbound in (outbound_alex.text, outbound_bailey.text):
        assert "Marigold Vex" not in outbound
        assert "Alex Fenwick" not in outbound
        assert "Bailey Kwan" not in outbound


# --- the rewrite tool itself ---------------------------------------------

def _write_pre_rename_submission(path: Path, *, canvas_id: str, submission_id: str,
                                 rep_id: str, text_with_old_pseudonym: str,
                                 submitted_at: str) -> None:
    """Write a submission dict directly, reproducing exactly what
    `Repository.append_submission` would have written before a rename: the
    (then-current) pseudonym baked into `raw_text`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {"schema": 1, "submissions": [{
        "submission_id": submission_id, "rep_id": rep_id, "canvas_id": canvas_id,
        "submitted_at": submitted_at, "raw_text": text_with_old_pseudonym,
        "student_word_count": len(text_with_old_pseudonym.split()),
        "segments": [{
            "span_start": 0, "span_end": len(text_with_old_pseudonym),
            "text": text_with_old_pseudonym, "origin": "student",
            "confidence": 1.0, "method": "residual",
        }],
        "flags": [], "scrub_findings": [{
            "kind": "roster_name", "replacement": "Legacy Otter",
            "span_start": text_with_old_pseudonym.find("Legacy Otter"),
            "span_end": text_with_old_pseudonym.find("Legacy Otter") + len("Legacy Otter"),
            "detail": "",
        }] if "Legacy Otter" in text_with_old_pseudonym else [],
    }]}
    path.write_text(json.dumps(document), encoding="utf-8")


def _repository_with_pre_rename_data(tmp_path: Path, *, canvas_id: str,
                                     old_pseudonym: str,
                                     new_pseudonym: str,
                                     partition: str = "2026-09") -> Repository:
    repository = Repository(
        tmp_path / "store",
        resolver=MappingResolver({canvas_id: new_pseudonym}), vault=None)
    repository.put_rep(_context())
    text = f"My essay mentions {old_pseudonym} directly, from before the rename."
    _write_pre_rename_submission(
        repository.root / "submissions" / f"{partition}.json",
        canvas_id=canvas_id, submission_id="pre-rename-1", rep_id=_REP_ID,
        text_with_old_pseudonym=text, submitted_at="2026-09-14T09:00:00-05:00")
    return repository


def test_a_span_stored_under_the_old_pseudonym_reads_with_the_new_one(tmp_path):
    repository = _repository_with_pre_rename_data(
        tmp_path, canvas_id="800003", old_pseudonym="Legacy Otter",
        new_pseudonym="Second Otter")

    report = rewrite_module.rewrite_pseudonym(
        repository, old_pseudonym="Legacy Otter", new_pseudonym="Second Otter")
    assert report.files_changed == 1
    assert report.submissions_changed == 1

    stored = repository.submissions_in_window(
        "Second Otter", date(2026, 1, 1), date(2026, 12, 31))[0]
    assert "Legacy Otter" not in stored.raw_text
    assert "Second Otter" in stored.raw_text
    for segment in stored.segments:
        assert "Legacy Otter" not in segment.text
    for finding in stored.scrub_findings:
        assert finding.replacement.lower() != "legacy otter"


def test_a_first_name_only_mention_is_rewritten_too(tmp_path):
    """A stored span may hold only the first name if that is all that
    matched at ingest -- the rewrite must catch that partial form too, not
    only the full two-word pseudonym."""
    repository = Repository(
        tmp_path / "store",
        resolver=MappingResolver({"800004": "Third Otter"}), vault=None)
    repository.put_rep(_context())
    text = "Legacy said the assignment was due Friday, so I started early."
    _write_pre_rename_submission(
        repository.root / "submissions" / "2026-09.json",
        canvas_id="800004", submission_id="pre-rename-firstname", rep_id=_REP_ID,
        text_with_old_pseudonym=text, submitted_at="2026-09-14T09:00:00-05:00")

    report = rewrite_module.rewrite_pseudonym(
        repository, old_pseudonym="Legacy Otter", new_pseudonym="Third Otter")
    assert report.submissions_changed == 1

    stored = repository.submissions_in_window(
        "Third Otter", date(2026, 1, 1), date(2026, 12, 31))[0]
    assert "Legacy" not in stored.raw_text
    assert "Third" in stored.raw_text


def test_rewrite_is_idempotent(tmp_path):
    repository = _repository_with_pre_rename_data(
        tmp_path, canvas_id="800005", old_pseudonym="Legacy Otter",
        new_pseudonym="Fourth Otter")
    path = repository.root / "submissions" / "2026-09.json"

    first = rewrite_module.rewrite_pseudonym(
        repository, old_pseudonym="Legacy Otter", new_pseudonym="Fourth Otter")
    assert first.submissions_changed == 1
    after_first = path.read_text(encoding="utf-8")

    second = rewrite_module.rewrite_pseudonym(
        repository, old_pseudonym="Legacy Otter", new_pseudonym="Fourth Otter")
    assert second.files_changed == 0
    assert second.submissions_changed == 0
    assert path.read_text(encoding="utf-8") == after_first


def test_rewrite_is_atomic_on_write_failure(tmp_path, monkeypatch):
    """A write failure mid-file must not leave a partially-rewritten file on
    disk: the original content must be exactly what is still there."""
    repository = _repository_with_pre_rename_data(
        tmp_path, canvas_id="800006", old_pseudonym="Legacy Otter",
        new_pseudonym="Fifth Otter")
    path = repository.root / "submissions" / "2026-09.json"
    before = path.read_text(encoding="utf-8")

    def _boom(*_args, **_kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(rewrite_module, "atomic_write_json", _boom)
    with pytest.raises(OSError):
        rewrite_module.rewrite_pseudonym(
            repository, old_pseudonym="Legacy Otter", new_pseudonym="Fifth Otter")

    assert path.read_text(encoding="utf-8") == before


def test_rewrite_dry_run_reports_without_writing(tmp_path):
    repository = _repository_with_pre_rename_data(
        tmp_path, canvas_id="800007", old_pseudonym="Legacy Otter",
        new_pseudonym="Sixth Otter")
    path = repository.root / "submissions" / "2026-09.json"
    before = path.read_text(encoding="utf-8")

    report = rewrite_module.rewrite_pseudonym(
        repository, old_pseudonym="Legacy Otter", new_pseudonym="Sixth Otter",
        dry_run=True)
    assert report.submissions_changed == 1
    assert path.read_text(encoding="utf-8") == before


def test_rewrite_falls_back_gracefully_with_no_rep_on_file(tmp_path):
    """No stored `AssignmentContext` for the rep (should not happen in a
    healthy store) -- the rewrite still replaces the text rather than
    losing the record or crashing."""
    repository = Repository(
        tmp_path / "store",
        resolver=MappingResolver({"800008": "Seventh Otter"}), vault=None)
    # Deliberately no put_rep() call.
    text = "My essay mentions Legacy Otter directly, from before the rename."
    _write_pre_rename_submission(
        repository.root / "submissions" / "2026-09.json",
        canvas_id="800008", submission_id="pre-rename-orphan", rep_id=_REP_ID,
        text_with_old_pseudonym=text, submitted_at="2026-09-14T09:00:00-05:00")

    report = rewrite_module.rewrite_pseudonym(
        repository, old_pseudonym="Legacy Otter", new_pseudonym="Seventh Otter")
    assert report.submissions_changed == 1
    stored = repository.submissions_in_window(
        "Seventh Otter", date(2026, 1, 1), date(2026, 12, 31))[0]
    assert "Legacy Otter" not in stored.raw_text
    assert "Seventh Otter" in stored.raw_text
