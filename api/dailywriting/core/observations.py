"""Evidence-backed noticings about one submission (INV-3).

Store the noticing, not the label. Every observation carries a dated, quoted
span from a specific submission, so a pattern in a profile can always be
traced back to the sentence that earned it and a teacher can disagree with it
on the evidence.

Two sources of observations, and the difference matters:

  - Failed checklist items, which mirror what the student already saw.
  - Independent detectors, which run whether or not the checker passed. This
    is where the Goodhart case lives: commentary that syntactically satisfies
    "explains how" while saying nothing passes `commentary_beyond_restatement`
    on purpose, and `commentary_formulaic` is what makes it visible in the
    teacher digest anyway.

Spans quoted here are already scrubbed, because submissions are scrubbed at
ingest and never stored otherwise. `assert_span_storable` is the belt to that
braces, and the repository calls it again on the way to disk.
"""
from __future__ import annotations

import re
from datetime import datetime

from api.dailywriting.core import scrub
from api.dailywriting.core.models import (
    PATTERN_TAGS,
    CriteriaSet,
    EvidenceRequiredError,
    Observation,
    PatternTagError,
    Score,
    SegmentationFlag,
    Submission,
    utc_now,
)

# Formulaic commentary reaches for these and stops there.
_EMPTY_STEMS = (
    "this shows that", "this shows how", "it shows that", "it shows how",
    "shows how important", "goes to show", "really shows", "just shows",
    "is trying to show", "this proves that", "this is important because",
    "which shows that",
)

_HEDGES = (
    "maybe", "sort of", "kind of", "i guess", "probably", "might be",
    "could be", "seems like", "a little bit", "i'm not sure", "im not sure",
    "or something", "i think maybe", "possibly",
)

_WORD = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)*")

_STOPWORDS = frozenset("""
a an the and or but so if then than that this these those there their they them
it its is are was were be been being am do does did done have has had can could
will would shall should may might must of to in on at by for with from about
into over under as not no nor too very just also only own same such more most
i you he she we us our your his her hers him my me mine what which who whom
how when where why while because although though during before after
""".split())

# Failed criterion to pattern tag. A criterion with no sensible tag is not
# given a made-up one: aggregation is only worth anything while the vocabulary
# stays honest.
_ITEM_PATTERNS: dict[str, str] = {
    "answers_prompt": "off_prompt",
    "specific": "thesis_too_general",
    # Both mean the thesis boundary is wrong: tier 1 by running past one
    # sentence, tier 2 and up by fusing the argument into the opening sentence.
    "one_sentence": "thesis_multi_sentence",
    "thesis_separate": "thesis_multi_sentence",
    "argument_matches_thesis": "argument_mismatched_to_thesis",
    "evidence_present": "evidence_missing",
    "evidence_relevant": "evidence_irrelevant",
    "evidence_integrated": "evidence_dropped_in_unintegrated",
    "commentary_beyond_restatement": "commentary_restates_evidence",
}


def _words(text: str) -> list[str]:
    return [m.group().lower() for m in _WORD.finditer(text or "")]


def _content(text: str) -> list[str]:
    return [w for w in _words(text) if w not in _STOPWORDS and len(w) > 2]


def _first_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return parts[0] if parts and parts[0] else (text or "").strip()


def assert_span_storable(span: str, vault=None) -> None:
    """Refuse a span that is empty or still carries a real name."""
    if not (span or "").strip():
        raise EvidenceRequiredError("an observation needs a quoted span")
    scrub.assert_clean_for_storage(span, vault)


def make_observation(
    *,
    pseudonym_id: str,
    submission_id: str,
    observed_at: datetime,
    pattern_tag: str,
    claim_text: str,
    evidence_span: str,
    criterion_id: str | None = None,
    source: str = "machine",
    vault=None,
) -> Observation:
    """Build one observation, refusing anything unaggregatable or unevidenced."""
    if pattern_tag not in PATTERN_TAGS:
        raise PatternTagError(
            f"pattern_tag {pattern_tag!r} is not in the controlled vocabulary; "
            "extend models.PATTERN_TAGS deliberately rather than inventing a "
            "tag at the call site, or the digest cannot aggregate it"
        )
    span = (evidence_span or "").strip()
    assert_span_storable(span, vault)
    return Observation(
        obs_id=f"{submission_id}:{pattern_tag}",
        pseudonym_id=pseudonym_id,
        submission_id=submission_id,
        observed_at=observed_at,
        criterion_id=criterion_id,
        pattern_tag=pattern_tag,
        claim_text=claim_text,
        evidence_span=span,
        source=source,  # type: ignore[arg-type]
    )


def _commentary_of(submission: Submission, score: Score) -> str:
    """Best available commentary text, from the checker's own span."""
    for item_id in ("commentary_beyond_restatement", "commentary_connects"):
        result = score.per_item.get(item_id)
        if result and result.evidence_span:
            return result.evidence_span.text
    return ""


def detect_formulaic_commentary(commentary: str,
                                reference: str = "") -> tuple[bool, str]:
    """Is this commentary syntactically fine and substantively empty?

    Three signals, any one of which is enough:

      - Stem density. It reaches for an explaining phrase at least once per
        sentence. Real commentary uses one occasionally; filler is built out
        of them.
      - Repetition. One content word carries a fifth of the whole explanation.
      - Restatement with a stem attached: an explaining phrase over almost no
        idea the thesis and quotation did not already contain.

    Deliberately not a novelty count on its own. Empty filler introduces plenty
    of new words ("really", "matters", "important"); what marks it is that the
    new words are scaffolding rather than content, which is what stem density
    measures and word novelty cannot.

    Returns (formulaic, reason). The reason lands in the observation's claim
    text, so the teacher sees what triggered it rather than a bare label.
    """
    if not (commentary or "").strip():
        return False, ""
    lowered = commentary.lower()
    stem_hits = sum(lowered.count(stem) for stem in _EMPTY_STEMS)
    sentence_count = max(1, len([s for s in re.split(r"(?<=[.!?])\s+", commentary)
                                 if s.strip()]))
    commentary_words = _content(commentary)

    if stem_hits >= 2 and stem_hits >= sentence_count:
        return True, (
            f"reaches for an explaining phrase {stem_hits} times across "
            f"{sentence_count} sentences, which is scaffolding rather than "
            "thinking"
        )
    if len(commentary_words) >= 12:
        counts: dict[str, int] = {}
        for word in commentary_words:
            counts[word] = counts.get(word, 0) + 1
        word, hits = max(counts.items(), key=lambda pair: (pair[1], pair[0]))
        if hits / len(commentary_words) >= 0.20:
            return True, (
                f"leans on the word \"{word}\" for {hits/len(commentary_words):.0%} "
                "of its content words"
            )
    if reference:
        novel = {w for w in commentary_words if w not in set(_content(reference))}
        if stem_hits >= 1 and len(novel) <= 2:
            return True, (
                f"attaches an explaining phrase to {len(novel)} idea word(s) "
                "the thesis and quotation did not already have"
            )
    return False, ""


# Shared verbatim between `observe_submission` and `observe_flags`: the same
# noticing must read the same way whether or not a `Score` exists to reach it
# from, and a copy in each function is how those two wordings would drift.
_NO_STUDENT_TEXT_CLAIM = ("This submission contains no writing of the "
                          "student's own; every word matches text they were "
                          "given.")


def _word_cap_observations(submission: Submission, add) -> None:
    for flag in submission.flags:
        if flag.code == "exceeds_word_cap":
            add("exceeds_word_cap", f"Over the word cap: {flag.detail}.",
                _first_sentence(submission.raw_text))


def observe_flags(
    submission: Submission,
    *,
    now: datetime | None = None,
    vault=None,
) -> list[Observation]:
    """Flag-derived observations for a submission with no `Score`.

    `core.ingest.ingest_unscored` calls this instead of `observe_submission`:
    an extended piece earns no criteria-derived observation, because there is
    no criteria comparison that ran, but `no_student_text` and
    `exceeds_word_cap` come from segmentation flags rather than from a
    checklist and are real noticings either way (ECR substrate brief, locked
    decision 3).
    """
    stamped = now or submission.submitted_at or utc_now()
    observations: list[Observation] = []

    def add(pattern_tag: str, claim: str, span: str) -> None:
        if not (span or "").strip():
            return
        observations.append(make_observation(
            pseudonym_id=submission.pseudonym_id,
            submission_id=submission.submission_id,
            observed_at=stamped,
            pattern_tag=pattern_tag,
            claim_text=claim,
            evidence_span=span.strip(),
            vault=vault,
        ))

    if any(flag.code == "no_student_text" for flag in submission.flags):
        add("no_student_text", _NO_STUDENT_TEXT_CLAIM,
            _first_sentence(submission.raw_text) or submission.raw_text[:120])
    _word_cap_observations(submission, add)

    return observations


def observe_submission(
    submission: Submission,
    score: Score,
    criteria_set: CriteriaSet,
    *,
    now: datetime | None = None,
    vault=None,
) -> list[Observation]:
    """Every observation this submission earns, each with its span.

    Deterministic and idempotent: `obs_id` is derived from the submission and
    the tag, so re-running ingest replaces rather than multiplies.

    `observed_at` defaults to the submission's own timestamp, not to now. An
    observation is dated to the work it is about, because that is what the
    profile window and the weekly digest select on: a teacher who ingests
    Monday's reps on Wednesday must not have Monday's noticings land in
    Wednesday's week, and a backfill must not push a term's observations into
    whatever week it happened to run.
    """
    stamped = now or submission.submitted_at or utc_now()
    observations: list[Observation] = []

    unlocatable = sorted(
        item.item_id
        for item in criteria_set.items
        if (result := score.per_item.get(item.item_id)) is not None
        and not result.met
        and result.evidence_span is None
        and (item.item_id == "arguable" or item.item_id in _ITEM_PATTERNS)
    )
    if (unlocatable
            and not any(flag.code == "unlocatable_evidence_span"
                        for flag in submission.flags)):
        submission.flags.append(SegmentationFlag(
            code="unlocatable_evidence_span",
            detail=("Unmet criterion could not be recorded because its "
                    "evidence span was not locatable: "
                    + ", ".join(unlocatable)),
        ))

    def add(pattern_tag: str, claim: str, span: str,
            criterion_id: str | None = None) -> None:
        if not (span or "").strip():
            # INV-3: no free-floating verdicts. A noticing we cannot quote is
            # a noticing we do not record.
            return
        observations.append(make_observation(
            pseudonym_id=submission.pseudonym_id,
            submission_id=submission.submission_id,
            observed_at=stamped,
            pattern_tag=pattern_tag,
            claim_text=claim,
            evidence_span=span.strip(),
            criterion_id=criterion_id,
            vault=vault,
        ))

    if score.status == "no_student_text":
        add("no_student_text", _NO_STUDENT_TEXT_CLAIM,
            _first_sentence(submission.raw_text) or submission.raw_text[:120])
        return observations

    for item in criteria_set.items:
        result = score.per_item.get(item.item_id)
        if result is None or result.met:
            continue
        span = result.evidence_span.text if result.evidence_span else ""

        if item.item_id == "arguable":
            restatement = "restates the question" in result.note
            add("restates_prompt" if restatement else "thesis_not_arguable",
                result.note.capitalize() + ".", span, item.item_id)
            continue

        tag = _ITEM_PATTERNS.get(item.item_id)
        if tag:
            add(tag, result.note.capitalize() + ".", span, item.item_id)

    # Independent detectors: these run whether or not the checker passed.
    commentary = _commentary_of(submission, score)
    if commentary:
        reference = " ".join([
            score.per_item.get("arguable").evidence_span.text
            if score.per_item.get("arguable")
            and score.per_item["arguable"].evidence_span else "",
            " ".join(s.text for s in submission.segments
                     if s.origin == "quoted_source"),
        ])
        formulaic, reason = detect_formulaic_commentary(commentary, reference)
        if formulaic:
            add("commentary_formulaic",
                f"The commentary {reason}.", commentary,
                "commentary_beyond_restatement")
        hedge = next((h for h in _HEDGES if h in commentary.lower()), None)
        if hedge:
            add("commentary_hedges",
                f"The commentary backs away from its own claim (\"{hedge}\").",
                commentary, "commentary_beyond_restatement")

    _word_cap_observations(submission, add)

    return observations
