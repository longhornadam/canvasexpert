"""The assistant-facing projection (api/dailywriting/projection.py).

Two acceptance criteria that are naturally store/projection-level rather than
MCP-tool-level (the tool-level criteria live in
api/tests/test_mcp_server_tools.py's "get_writing_history" section):

  AC6  a field a future Submission/Score/Observation never declared, but that
       somehow reached a stored document, must not reach the projection.
  AC8  no new module under api/dailywriting/ imports Canvas transport.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from api.dailywriting import projection
from api.dailywriting.config import criteria_loader
from api.dailywriting.core import ingest as ingest_module
from api.dailywriting.fixtures import loader
from api.dailywriting.store import repo as repo_module
from api.dailywriting.store.repo import Repository


def _ingest_one(fixture_number: int, roster_map):
    raw = loader.single(fixture_number)
    context = loader.rep(raw["rep_id"])
    criteria = criteria_loader.load_tier(context.tier)
    result = ingest_module.ingest(
        submission_id=raw["submission_id"], rep_id=raw["rep_id"],
        pseudonym_id=loader.pseudonym_for(raw["canvas_id"]),
        submitted_at=loader.submitted_at(raw), text=raw["text"],
        context=context, criteria_set=criteria,
        roster_map=roster_map, protected=set(),
    )
    return context, result


def test_the_codec_ignores_an_unexpected_key_on_a_stored_document(tmp_path):
    """Codec robustness, not the projection: `codec.submission_from_dict`
    (store/codec.py:193-206) builds a `Submission` by naming each field
    explicitly, so a hand-edited extra key on disk is gone before the
    projection ever sees the object -- this proves the store layer is
    forgiving of an unknown key, which the real AC6 claim (below) does not
    get to assume for free. A `projection.py` that did
    `row.update(vars(submission))` would pass this test identically, which is
    why it is not, on its own, the AC6 test."""
    roster_map = loader.roster_map()
    repository = Repository(tmp_path / "store", resolver=loader.resolver(),
                            vault=None)
    context, result = _ingest_one(1, roster_map)
    repository.put_rep(context)
    repository.append_submission(result.submission)
    repository.append_score(result.score, result.submission.pseudonym_id)
    repository.append_observations(result.observations)

    partition = repository._partition(result.submission.submitted_at)
    path = repository.root / repo_module.SUBMISSIONS / f"{partition}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert len(document["submissions"]) == 1
    document["submissions"][0]["diagnosis"] = "should never leave this machine"
    path.write_text(json.dumps(document), encoding="utf-8")

    pseudonym = result.submission.pseudonym_id
    window = (result.submission.submitted_at.date(),
             result.submission.submitted_at.date())
    submissions = repository.submissions_in_window(pseudonym, *window)
    assert len(submissions) == 1  # the hand-edited entry still reads back
    assert not hasattr(submissions[0], "diagnosis")


def test_the_projection_drops_a_field_no_dataclass_ever_declared(tmp_path):
    """AC6, for real this time: attach a genuinely undeclared attribute to a
    live `Submission` instance (bypassing the codec entirely -- frozen
    dataclasses refuse a normal `submission.diagnosis = ...`, so this reaches
    past that with `object.__setattr__`), then call `build_history_payload`
    directly. Only a hand-named whitelist rebuild -- never `vars()`,
    `dataclasses.asdict`, or `__dict__` -- can possibly drop this, because
    there is no codec step in between to have quietly done it first."""
    roster_map = loader.roster_map()
    _, result = _ingest_one(1, roster_map)
    submission = result.submission
    object.__setattr__(submission, "diagnosis", "should never leave this machine")
    assert submission.diagnosis == "should never leave this machine"  # sanity

    context = loader.rep(submission.rep_id)
    payload = projection.build_history_payload(
        pseudonym_id=submission.pseudonym_id, current_tier=1,
        since=submission.submitted_at.date(), until=submission.submitted_at.date(),
        submissions=[submission], scores={result.submission.submission_id: result.score},
        observations=result.observations, reps={submission.rep_id: context},
        directives=[], profile=None, include_text=True, max_text_chars=0,
    )
    dumped = json.dumps(payload)
    assert "diagnosis" not in dumped
    assert "should never leave this machine" not in dumped
    # The rest of the row still came through -- proves this is a whitelist
    # drop, not a crash that happened to swallow the field along with
    # everything else.
    assert payload["submissions"][0]["submission_id"] == submission.submission_id


def test_build_history_payload_sorts_regardless_of_input_order():
    """AC1's "ascending by date" is the projection's own contract, not
    something borrowed from `Repository.submissions_in_window` (which already
    returns pre-sorted results at repo.py:363-365 -- so a test that goes
    through the repository, no matter how the fixtures are dated or appended,
    structurally cannot fail if `build_history_payload`'s own `sorted(...)`
    call were deleted). This calls the projection directly with two
    submissions passed in reverse chronological order and nothing else in
    between to have sorted them first."""
    roster_map = loader.roster_map()
    raw = loader.single(1)
    context = loader.rep(raw["rep_id"])
    criteria = criteria_loader.load_tier(context.tier)
    pseudonym = loader.pseudonym_for(raw["canvas_id"])

    def _submission_on(day: int):
        return ingest_module.ingest(
            submission_id=f"sub-order-{day}", rep_id=raw["rep_id"],
            pseudonym_id=pseudonym,
            submitted_at=datetime(2026, 9, day, 9, 0, tzinfo=timezone.utc),
            text=raw["text"], context=context, criteria_set=criteria,
            roster_map=roster_map, protected=set(),
        ).submission

    early, late = _submission_on(5), _submission_on(20)
    payload = projection.build_history_payload(
        pseudonym_id=pseudonym, current_tier=1,
        since=date(2026, 9, 1), until=date(2026, 9, 30),
        submissions=[late, early],  # deliberately out of order
        scores={}, observations=[], reps={context.rep_id: context},
        directives=[], profile=None, include_text=False, max_text_chars=0,
    )
    assert [row["submission_id"] for row in payload["submissions"]] == [
        early.submission_id, late.submission_id]


def test_projection_module_imports_no_canvas_transport():
    """AC8: no new module under api/dailywriting/ imports api.canvas,
    requests, or any Canvas transport. Source-text check, deliberately not an
    import-graph walk: this package has no Canvas token and no network, and a
    text grep is the cheapest thing that cannot be fooled by a lazy import
    inside a function body either."""
    source = Path(projection.__file__).read_text(encoding="utf-8")
    for forbidden in ("import requests", "api.canvas", "canvas_client",
                     "api.webui.canvas_client"):
        assert forbidden not in source, (
            f"api/dailywriting/projection.py must not reference {forbidden!r}")
