"""Evidence-store coverage for the retained Writing Record path."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

from api.dailywriting import projection
from api.dailywriting.core import ingest
from api.dailywriting.fixtures import loader
from api.dailywriting.store import repo as repo_module
from api.dailywriting.store.repo import Repository
from api import feedback_safety


def _submission(number: int):
    raw = loader.single(number)
    context = loader.rep(raw["rep_id"])
    return context, ingest.ingest(
        submission_id=raw["submission_id"], rep_id=raw["rep_id"],
        pseudonym_id=loader.pseudonym_for(raw["canvas_id"]),
        submitted_at=loader.submitted_at(raw), text=raw["text"],
        context=context, roster_map=loader.roster_map(),
    )


def _shape(submission):
    return {
        "submission_id": submission.submission_id,
        "rep_id": submission.rep_id,
        "submitted_at": submission.submitted_at.isoformat(),
        "raw_text_digest": hashlib.sha256(submission.raw_text.encode()).hexdigest(),
        "student_word_count": submission.student_word_count,
        "segments": [(s.origin, s.span_start, s.span_end) for s in submission.segments],
        "flags": [flag.code for flag in submission.flags],
        "findings": [(f.kind, f.replacement, f.span_start, f.span_end) for f in submission.scrub_findings],
    }


def test_pinned_fixture_evidence_shape_survives_store_round_trip(tmp_path):
    repository = Repository(tmp_path / "store", resolver=loader.resolver(), vault=None)
    for number in loader.single_numbers():
        context, submission = _submission(number)
        before = _shape(submission)
        repository.put_rep(context)
        repository.append_submission(submission)
        restored = {item.submission_id: item for item in repository.submissions_in_window(submission.pseudonym_id, date(2026, 1, 1), date(2026, 12, 31))}
        after = _shape(restored[submission.submission_id])
        assert after == before


def test_reingest_reads_one_current_submission_and_one_assignment(tmp_path):
    context, submission = _submission(1)
    repository = Repository(tmp_path / "store", resolver=loader.resolver(), vault=None)
    repository.put_rep(context)
    repository.append_submission(submission)
    repository.put_rep(context)
    repository.append_submission(submission)
    assert len(repository.submissions_in_window(submission.pseudonym_id, date(2026, 1, 1), date(2026, 12, 31))) == 1
    assert repository.read_rep(context.rep_id) == context


def test_projection_allowlists_evidence_and_gates_text():
    context, submission = _submission(7)
    hidden = projection.build_history_payload(pseudonym_id=submission.pseudonym_id, since=date(2026, 1, 1), until=date(2026, 12, 31), submissions=[submission], reps={context.rep_id: context}, include_text=False, max_text_chars=20)
    shown = projection.build_history_payload(pseudonym_id=submission.pseudonym_id, since=date(2026, 1, 1), until=date(2026, 12, 31), submissions=[submission], reps={context.rep_id: context}, include_text=True, max_text_chars=20)
    assert set(hidden) == {"pseudonym", "window_start", "window_end", "submissions"}
    assert "raw_text" not in json.dumps(hidden)
    assert "raw_text" in shown["submissions"][0]
    assert {"origin", "span_start", "span_end", "method", "confidence"} <= set(hidden["submissions"][0]["segments"][0])


def test_projection_sorts_its_own_input_order():
    context, submission = _submission(1)
    late = replace(submission, submission_id="late", submitted_at=datetime(2026, 9, 20, tzinfo=timezone.utc))
    early = replace(submission, submission_id="early", submitted_at=datetime(2026, 9, 5, tzinfo=timezone.utc))
    payload = projection.build_history_payload(pseudonym_id=submission.pseudonym_id, since=date(2026, 9, 1), until=date(2026, 9, 30), submissions=[late, early], reps={context.rep_id: context}, include_text=False, max_text_chars=0)
    assert [row["submission_id"] for row in payload["submissions"]] == ["early", "late"]


def test_clean_include_text_payload_passes_actual_safety_gate():
    context, submission = _submission(8)
    payload = projection.build_history_payload(pseudonym_id=submission.pseudonym_id, since=date(2026, 1, 1), until=date(2026, 12, 31), submissions=[submission], reps={context.rep_id: context}, include_text=True, max_text_chars=0)
    class Vault:
        def all_real_identifiers(self):
            return loader.real_names(), {entry["canvas_id"] for entry in loader.vault_entries()}
    verdict = feedback_safety.scan_payload(payload, Vault())
    assert verdict["hard"] == []
    assert verdict["soft"] == []


def test_flag_detail_is_registered_and_scanned():
    verdict = feedback_safety.scan_payload({"flag_detail": "Marcus Bell 990001"}, type("Vault", (), {"all_real_identifiers": lambda self: ({"Marcus Bell"}, {"990001"})})())
    assert verdict["green"] is False
    assert verdict["hard"]
    assert "flag_detail" in feedback_safety._TEXT_FIELDS


def test_projection_imports_no_canvas_transport():
    source = Path(projection.__file__).read_text(encoding="utf-8")
    for forbidden in ("import requests", "api.canvas", "canvas_client"):
        assert forbidden not in source


def test_codec_ignores_unknown_stored_field(tmp_path):
    context, submission = _submission(1)
    repository = Repository(tmp_path / "store", resolver=loader.resolver(), vault=None)
    repository.put_rep(context)
    repository.append_submission(submission)
    path = repository.root / repo_module.SUBMISSIONS / f"{submission.submitted_at:%Y-%m}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["submissions"][0]["diagnosis"] = "private"
    path.write_text(json.dumps(document), encoding="utf-8")
    restored = repository.submissions_in_window(submission.pseudonym_id, date(2026, 1, 1), date(2026, 12, 31))[0]
    assert not hasattr(restored, "diagnosis")


def test_ingest_returns_submission_directly():
    context = loader.rep("rep_t1_phones")
    submission = ingest.ingest(submission_id="direct", rep_id=context.rep_id, pseudonym_id="Sparky McGee", submitted_at=datetime(2026, 9, 1, tzinfo=timezone.utc), text="A short response.", context=context, roster_map=[])
    assert submission.submission_id == "direct"
