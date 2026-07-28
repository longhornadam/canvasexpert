"""INV-1: scoring is history-blind. Acceptance tests T-1, T-2, T-14."""
from __future__ import annotations

import ast
import inspect
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from api.dailywriting.config import criteria_loader
from api.dailywriting.core import scoring
from api.dailywriting.core.models import (
    PatternSummary,
    Segment,
    build_profile,
)
from api.dailywriting.fixtures import loader
from api.dailywriting.store import codec

FIXED_NOW = datetime(2026, 11, 10, 6, 30, tzinfo=timezone.utc)

# The scorer may see the model, the thresholds, and the standard library.
# Anything that could reach a student's record is forbidden by name.
FORBIDDEN_IMPORT_TOKENS = (
    "profile", "observations", "directives", "digest", "feedback",
    "store", "repo", "codec", "identity", "vault", "roster", "ingest",
    "segmentation", "scrub",
)

# `now` is a clock, `submission_id` names the artifact, and `raw_text` gives
# the scorer only the scrubbed text geometry needed to return exact evidence
# slices. None can be exchanged for a student, because the import check above
# proves this module cannot reach anything that would do the exchanging.
ALLOWED_EXTRA_PARAMS = {"now", "submission_id", "raw_text"}

HISTORY_PARAM_NAMES = {
    "profile", "pseudonym_id", "pseudonym", "history", "record", "records",
    "student", "student_id", "observations", "directives", "vault", "roster",
    "repo", "store", "source", "prior_scores",
}


def _imported_names(module) -> list[str]:
    tree = ast.parse(Path(inspect.getsourcefile(module)).read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            found.extend(f"{base}.{alias.name}" for alias in node.names)
    return found


def test_t1_scoring_signature_cannot_reach_history():
    """T-1: `score_submission` has no parameter reachable to history."""
    signature = inspect.signature(scoring.score_submission)
    positional = [
        name for name, param in signature.parameters.items()
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
    ]
    assert positional == ["student_segments", "criteria_set",
                          "assignment_context"], (
        "the required signature shape changed; scoring must take student "
        "segments, a criteria set, and assignment context and nothing else"
    )
    extra = set(signature.parameters) - set(positional)
    assert extra <= ALLOWED_EXTRA_PARAMS, (
        f"unexpected parameter(s) {sorted(extra - ALLOWED_EXTRA_PARAMS)} on the "
        "history-blind scorer"
    )
    assert not (set(signature.parameters) & HISTORY_PARAM_NAMES)


def test_t1_scoring_module_imports_nothing_that_reaches_history():
    """T-1, static: the scorer could not read a record even if it wanted to."""
    for name in _imported_names(scoring):
        lowered = name.lower()
        # `core.models` is the record *shape*, not a record source.
        if lowered.endswith("models") or ".models." in lowered:
            continue
        for token in FORBIDDEN_IMPORT_TOKENS:
            assert token not in lowered, (
                f"core/scoring.py imports {name!r}, which can reach student "
                "history; INV-1 says the scorer must not be able to"
            )


def test_t1_check_input_carries_no_student_handle():
    """A check sees text and criteria. There is nowhere for history to hide."""
    fields = set(scoring.CheckInput.__dataclass_fields__)
    assert not (fields & HISTORY_PARAM_NAMES)


def _tier1_case():
    raw = loader.single(1)
    context = loader.rep(raw["rep_id"])
    criteria = criteria_loader.load_tier(1)
    segments = [Segment(span_start=0, span_end=len(raw["text"]),
                        text=raw["text"], origin="student", confidence=1.0,
                        method="residual")]
    return segments, criteria, context


def test_t2_identical_text_scores_identically_under_opposite_profiles():
    """T-2: two maximally different profiles, byte-identical Score."""
    segments, criteria, context = _tier1_case()

    strong = build_profile(
        pseudonym_id="Sparky McGee",
        generated_at=FIXED_NOW,
        window_start=date(2026, 10, 17),
        window_end=date(2026, 11, 14),
        tier=4,
        per_criterion_rate={item.item_id: 1.0 for item in criteria.items},
        active_patterns=[],
        open_directives=[],
        best_piece=None,
        next_focus="Nothing; this student is ready to move up.",
        ready_for_tier_advance=True,
    )
    struggling = build_profile(
        pseudonym_id="Rutabaga Sandwich",
        generated_at=FIXED_NOW,
        window_start=date(2026, 10, 17),
        window_end=date(2026, 11, 14),
        tier=1,
        per_criterion_rate={item.item_id: 0.0 for item in criteria.items},
        active_patterns=[PatternSummary(
            pattern_tag="restates_prompt", count=9, rate=1.0,
            evidence=["Students should be allowed to keep their phones."],
            first_seen=date(2026, 10, 17), last_seen=date(2026, 11, 14))],
        open_directives=[],
        best_piece=None,
        next_focus="Take a side instead of repeating the question.",
        ready_for_tier_advance=False,
    )
    assert strong != struggling

    first = scoring.score_submission(segments, criteria, context,
                                     submission_id="sub-f01", now=FIXED_NOW)
    second = scoring.score_submission(segments, criteria, context,
                                      submission_id="sub-f01", now=FIXED_NOW)

    assert first == second
    serialize = lambda score: json.dumps(  # noqa: E731
        codec.score_to_dict(score, canvas_id="990001"), sort_keys=True)
    assert serialize(first) == serialize(second)
    assert first.history_blind is True


def test_t2_scorer_refuses_a_profile_argument():
    """Structural, not conventional: passing a profile is a TypeError."""
    segments, criteria, context = _tier1_case()
    profile = build_profile(
        pseudonym_id="Sparky McGee", generated_at=FIXED_NOW,
        window_start=date(2026, 10, 17), window_end=date(2026, 11, 14),
        tier=1, per_criterion_rate={}, active_patterns=[], open_directives=[],
        best_piece=None, next_focus="", ready_for_tier_advance=False)
    with pytest.raises(TypeError):
        scoring.score_submission(segments, criteria, context, profile=profile)
    with pytest.raises(TypeError):
        scoring.score_submission(segments, criteria, context,
                                 pseudonym_id="Sparky McGee")


def test_t14_criteria_must_be_published_before_the_work():
    """T-14: scoring work that predates its checklist raises."""
    segments, criteria, context = _tier1_case()
    from dataclasses import replace

    late = replace(criteria,
                   published_at=datetime(2026, 12, 1, 8, 0,
                                         tzinfo=timezone(timedelta(hours=-6))))
    with pytest.raises(scoring.CriteriaNotPublishedError):
        scoring.score_submission(segments, late, context, now=FIXED_NOW)


def test_t14_publication_guard_takes_no_student_handle():
    """The submitted_at form of the guard is callable without a person."""
    published = datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)
    submitted = datetime(2026, 9, 14, 14, 12, tzinfo=timezone.utc)
    with pytest.raises(scoring.CriteriaNotPublishedError):
        scoring.assert_criteria_published(published, submitted)
    scoring.assert_criteria_published(submitted, published)

    signature = inspect.signature(scoring.assert_criteria_published)
    assert list(signature.parameters) == ["published_at", "measured_at"]
