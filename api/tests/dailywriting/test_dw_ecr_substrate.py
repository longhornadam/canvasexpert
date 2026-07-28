"""Substrate support for extended writing (an ECR) in the longitudinal record.

Acceptance criteria from
docs/handoffs/CanvasExpert-WritingRecord-ECRSubstrate-BRIEF.md Sec 5:
AC1 (unscored ingest), AC3's structural half (`IngestResult.score` stays
required), and AC6's store round-trip half (the dead `unknown` Origin value;
the segmentation-level half lives in test_dw_segmentation.py).

AC2 (`get_writing_history` returns null total/possible/status end to end) is
a tool-level criterion and lives in api/tests/test_mcp_server_tools.py's
"get_writing_history" section, alongside every other test of that tool.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

from api.dailywriting.core import ingest as ingest_module
from api.dailywriting.fixtures import loader
from api.dailywriting.store.repo import Repository

# A deterministic, multi-paragraph essay built from a vocabulary that shares
# no words with any fixture rep's prompt, scaffold, or source text, so every
# word segmentation produces is unambiguously the student's own. Four
# paragraphs of 225 words apiece land at exactly 900.
_VOCABULARY = (
    "mill town grew slowly around the river bend and each generation added "
    "its own memory to the same stretch of water without writing any of it "
    "down before deciding whether to stay or leave for a city that promised "
    "something steadier than lumber prices ever could across three "
    "different decades of families who kept working the same shift"
).split()


def _essay(total_words: int, paragraphs: int = 4) -> str:
    per_paragraph, remainder = divmod(total_words, paragraphs)
    counter = 0
    blocks = []
    for index in range(paragraphs):
        count = per_paragraph + (remainder if index == paragraphs - 1 else 0)
        words = [_VOCABULARY[(counter + i) % len(_VOCABULARY)]
                 for i in range(count)]
        counter += count
        blocks.append(" ".join(words) + ".")
    return "\n\n".join(blocks)


def test_ingest_unscored_produces_a_correct_unscored_submission(roster_map):
    """AC1: a 900-word multi-paragraph submission ingests through the
    unscored path with correct student_word_count, no Score, and no
    criteria-derived observations -- and no exception, with no CriteriaSet
    supplied (ingest_unscored's signature has no such parameter at all)."""
    # No word cap, no scaffold, no source passage -- a clean essay against
    # this rep trips no segmentation flag at all.
    context = loader.rep("rep_t4_seq_01")
    text = _essay(900)
    pseudonym_id = loader.pseudonym_for(loader.vault_entries()[0]["canvas_id"])

    result = ingest_module.ingest_unscored(
        submission_id="ecr-ac1", rep_id=context.rep_id,
        pseudonym_id=pseudonym_id,
        submitted_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        text=text, context=context, roster_map=roster_map,
    )

    assert result.submission.student_word_count == 900
    assert not hasattr(result, "score")
    # No no_student_text / exceeds_word_cap flag fired on a clean 900-word
    # essay against a rep with no word cap, so no flag-derived observation
    # exists to fabricate a criteria-derived one out of.
    assert result.observations == []
    assert result.submission.flags == []


def test_ingest_unscored_still_keeps_flag_derived_observations(roster_map):
    """AC1's companion claim (Sec 3.3): a flag-derived observation still
    applies to an unscored piece. Reuses fixture 5 (the empty-stem-blank
    submission, which trips no_student_text) so this exercises the real
    segmentation flag rather than a hand-built one."""
    raw = loader.single(5)
    context = loader.rep(raw["rep_id"])

    result = ingest_module.ingest_unscored(
        submission_id="ecr-ac1-flag", rep_id=context.rep_id,
        pseudonym_id=loader.pseudonym_for(raw["canvas_id"]),
        submitted_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        text=raw["text"], context=context, roster_map=roster_map,
    )

    assert result.submission.student_word_count == 0
    tags = {o.pattern_tag for o in result.observations}
    assert "no_student_text" in tags


def test_ingest_result_score_field_remains_required():
    """AC3's structural claim: the scored path's `IngestResult.score` is
    still a required, non-None field -- the brief's whole reason for adding a
    sibling function instead of threading an Optional score through it."""
    score_field = next(f for f in dataclasses.fields(ingest_module.IngestResult)
                       if f.name == "score")
    assert score_field.default is dataclasses.MISSING
    assert score_field.default_factory is dataclasses.MISSING


def test_unscored_submission_round_trips_with_no_dead_origin_value(
        tmp_path, roster_map):
    """AC6's store half: an unscored submission's segments -- which include a
    quoted_source segment, exercising a non-trivial origin -- round-trip
    through Repository.append_submission / submissions_in_window with the
    same origin set, and that set never contains the removed `unknown`
    value."""
    raw = loader.single(6)  # rep_t3_forest: has a quoted_source segment
    context = loader.rep(raw["rep_id"])
    pseudonym_id = loader.pseudonym_for(raw["canvas_id"])

    result = ingest_module.ingest_unscored(
        submission_id="ecr-ac6", rep_id=context.rep_id,
        pseudonym_id=pseudonym_id,
        submitted_at=datetime(2026, 10, 2, tzinfo=timezone.utc),
        text=raw["text"], context=context, roster_map=roster_map,
    )
    origins_before = {s.origin for s in result.submission.segments}
    assert "quoted_source" in origins_before  # a non-trivial origin is present

    repository = Repository(tmp_path / "store", resolver=loader.resolver(),
                            vault=None)
    repository.put_rep(context)
    repository.append_submission(result.submission)

    window = (result.submission.submitted_at.date(),) * 2
    stored = repository.submissions_in_window(pseudonym_id, *window)
    assert len(stored) == 1
    origins_after = {s.origin for s in stored[0].segments}

    assert origins_after == origins_before
    assert "unknown" not in origins_after
