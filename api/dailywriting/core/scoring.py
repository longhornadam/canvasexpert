"""History-blind checklist scoring (INV-1).

The score is criterion-referenced. The same text against the same criteria set
produces an identical result regardless of who wrote it or what their record
says, and this module is structured so that it *cannot* do otherwise: it
imports the model, the thresholds, and the standard library, and nothing that
can reach a profile, an observation, a directive, a roster, or the store.
`api/tests/dailywriting/test_dw_history_blind.py` asserts that import set
statically, so widening it fails the suite rather than review.

Two parameters need a word of justification, because both look like leaks and
neither is one:

  `now` is a clock. A Score records when it was produced; injecting the clock
  is what makes byte-identical output testable at all.

  `submission_id` names the artifact being scored, not the person who wrote
  it. It is an opaque record id, and this module has no way to exchange one
  for a student, because it cannot import the store. What the handoff forbids
  is a *person* handle, and there is deliberately no `pseudonym_id` here, not
  even for logging.

The checks are deterministic heuristics, and they are honest about their
limits. Where no rule can settle a criterion, the result carries
`needs_judgment=True` rather than a confident guess: a checker that silently
rules on "is this arguable" makes the whole instrument unfalsifiable, and the
monthly blind-calibration sample in `core.digest` exists to catch it when it
drifts. A model-judged path replaces these one criterion at a time; the
production prompts are out of scope here and marked as stubs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from api.dailywriting.config import thresholds
from api.dailywriting.core.models import (
    AssignmentContext,
    CriteriaSet,
    ItemResult,
    Score,
    Segment,
    Span,
    utc_now,
)

SCORER_VERSION = "dw-checklist-1"


class CriteriaNotPublishedError(ValueError):
    """Criteria must be published before students are measured against them."""


class UnknownCheckError(ValueError):
    """A criteria file named a check this scorer does not implement."""


# --- Lexicons ---------------------------------------------------------------

_STOPWORDS = frozenset("""
a an the and or but so if then than that this these those there their they them
it its is are was were be been being am do does did done have has had can could
will would shall should may might must of to in on at by for with from about
into over under as not no nor too very just also only own same such more most
i you he she we us our your his her hers him my me mine what which who whom
how when where why while because although though during before after
""".split())

# A position takes a side. These are the words a 7th grader uses to do it.
_STANCE_MARKERS = (
    "should", "should not", "shouldn't", "must", "need to", "needs to",
    "better", "worse", "best", "worst", "more important", "most important",
    "because", "since", "even though", "rather than", "instead of",
    "fails", "succeeds", "proves", "matters", "responsible", "to blame",
    "wrong", "right", "unfair", "fair", "harmful", "helpful", "causes",
    "is not", "isn't", "are not", "aren't", "does not", "doesn't",
)

# Commentary that reaches for meaning uses these. Their presence is not proof
# of thought, which is precisely why `observations` runs a formulaic check
# alongside: the Goodhart case passes here on purpose and is caught there.
_INTERPRETIVE_MARKERS = (
    "reveals", "suggests", "shows that", "means that", "proves that",
    "because", "which is why", "in other words", "the reason",
    "this is important because", "matters because", "so that",
    "implies", "hints", "points to", "tells us",
)

_HEDGES = ("maybe", "sort of", "kind of", "i guess", "probably", "might be",
           "could be", "seems like", "i think maybe", "a little bit")

_VAGUE_NOUNS = frozenset({
    "thing", "things", "stuff", "someone", "something", "anything", "people",
    "society", "everyone", "everybody", "everything", "it", "they", "them",
    "world", "way", "ways", "lot", "lots", "bad", "good", "nice",
})

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[\s ]+")
_WORD = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)*")


# --- Text helpers -----------------------------------------------------------


def _words(text: str) -> list[str]:
    return [m.group().lower() for m in _WORD.finditer(text or "")]


def _content_words(text: str) -> set[str]:
    return {w for w in _words(text) if w not in _STOPWORDS and len(w) > 2}


def _share_present(needle: set[str], haystack: set[str]) -> float:
    """Share of `needle` found in `haystack`. 0.0 when there is nothing to ask."""
    if not needle:
        return 0.0
    return len(needle & haystack) / len(needle)


def _sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_SPLIT.split((text or "").strip())]
    return [p for p in parts if p]


def _contains_any(text: str, needles: tuple[str, ...]) -> str | None:
    lowered = (text or "").lower()
    for needle in needles:
        if needle in lowered:
            return needle
    return None


def _span_for_match(
    text: str,
    match: re.Match[str],
    *,
    raw_text: str | None = None,
    offsets: list[int] | None = None,
    base: int = 0,
) -> Span:
    if raw_text is not None and offsets is not None:
        start = offsets[match.start()]
        end = offsets[match.end() - 1] + 1
        return Span(start, end, raw_text[start:end])
    return Span(base + match.start(), base + match.end(), match.group())


def _span_of(
    text: str,
    fragment: str,
    base: int = 0,
    *,
    raw_text: str | None = None,
    offsets: list[int] | None = None,
) -> Span | None:
    """Locate a scorer fragment without storing its reconstructed spelling.

    Checks reason over sentence lists, which deliberately normalise whitespace.
    The stored span must instead be a literal slice of the scrubbed submission,
    including its original paragraph breaks and spacing.
    """
    if not fragment:
        return None
    words = re.split(r"\s+", fragment.strip())
    if not words:
        return None
    match = re.search(r"\s+".join(re.escape(word) for word in words), text or "")
    if match is None:
        return None
    return _span_for_match(text, match, raw_text=raw_text, offsets=offsets,
                           base=base)


def _quoted_span(
    text: str,
    *,
    raw_text: str | None = None,
    offsets: list[int] | None = None,
) -> Span | None:
    """Return the first literal quotation only as evidence geometry.

    This does not change the checker’s distinction between a quotation that
    matches assigned source text and quotation marks of unknown provenance.
    It merely gives the existing verdict an honest, quoteable location.
    """
    match = re.search(r'["“][^"”]+["”]', text or "")
    if match is None:
        return None
    return _span_for_match(text, match, raw_text=raw_text, offsets=offsets)


# --- The bundle a check sees -------------------------------------------------


@dataclass(frozen=True)
class CheckInput:
    """Everything a check may look at. Provided text is labeled as provided.

    Note what is absent: no student handle, no record, no prior score. A check
    that wanted history would have nowhere to get it.
    """

    scored_text: str      # student prose plus legitimately quoted source
    raw_text: str         # stored scrubbed submission; every Span points here
    scored_offsets: list[int] | None  # scored_text positions into raw_text
    student_text: str     # student prose only
    quoted_text: str      # quoted source only
    provided_text: str    # prompt and scaffolds, labeled context
    context: AssignmentContext
    student_word_count: int

    @property
    def sentences(self) -> list[str]:
        return _sentences(self.scored_text)

    @property
    def thesis(self) -> str:
        """First sentence. At tier 1 that is the whole submission."""
        found = self.sentences
        return found[0] if found else ""

    @property
    def after_thesis(self) -> str:
        return " ".join(self.sentences[1:])

    @property
    def commentary(self) -> str:
        """Sentences after the one carrying the quotation.

        Falls back to everything after the thesis when nothing was quoted, so
        a tier-4 response with no evidence still gets its commentary read
        rather than silently scoring zero on two separate criteria for the
        same missing quote.
        """
        found = self.sentences
        if self.quoted_text.strip():
            marker = _words(self.quoted_text)[:4]
            for index, sentence in enumerate(found):
                if marker and all(w in _words(sentence) for w in marker):
                    return " ".join(found[index + 1:])
        return self.after_thesis

    def span_of(self, fragment: str) -> Span | None:
        return _span_of(self.scored_text, fragment, raw_text=self.raw_text,
                        offsets=self.scored_offsets)

    @property
    def evidence_span(self) -> Span | None:
        found = self.span_of(self.quoted_text.strip())
        if found is None and '"' in self.scored_text:
            return _quoted_span(self.scored_text, raw_text=self.raw_text,
                                offsets=self.scored_offsets)
        return found


CheckFn = Callable[[CheckInput], ItemResult]


def _result(item_id: str, met: bool, note: str, *,
            span: Span | None = None,
            needs_judgment: bool = False) -> ItemResult:
    return ItemResult(item_id=item_id, met=met, evidence_span=span,
                      note=note, needs_judgment=needs_judgment)


# --- Checks -----------------------------------------------------------------
# Each check is named by `CriterionItem.check_id` in the criteria JSON.


def check_answers_prompt(inp: CheckInput) -> ItemResult:
    prompt_words = _content_words(inp.context.prompt_text)
    student_words = _content_words(inp.scored_text)
    share = _share_present(prompt_words, student_words)
    met = share >= thresholds.ANSWERS_PROMPT_OVERLAP
    return _result(
        "answers_prompt", met,
        f"{share:.0%} of the prompt's key words appear in the response",
        span=inp.span_of(inp.thesis),
    )


def check_thesis_arguable(inp: CheckInput) -> ItemResult:
    thesis_words = _content_words(inp.thesis)
    prompt_words = _content_words(inp.context.prompt_text)
    borrowed = _share_present(thesis_words, prompt_words)
    if borrowed >= thresholds.RESTATEMENT_OVERLAP:
        return _result(
            "thesis_arguable", False,
            f"{borrowed:.0%} of this thesis is the prompt's own wording, so it "
            "restates the question instead of taking a side",
            span=inp.span_of(inp.thesis),
        )
    marker = _contains_any(inp.thesis, _STANCE_MARKERS)
    if marker:
        return _result(
            "thesis_arguable", True,
            f"takes a position someone could disagree with (\"{marker}\")",
            span=inp.span_of(inp.thesis),
        )
    return _result(
        "thesis_arguable", False,
        "no stance language found; a reader could not tell what is being "
        "argued. Needs a human or model read before this counts as settled",
        span=inp.span_of(inp.thesis),
        needs_judgment=True,
    )


def check_thesis_specific(inp: CheckInput) -> ItemResult:
    thesis_words = _words(inp.thesis)
    content = _content_words(inp.thesis)
    concrete = content - _VAGUE_NOUNS
    if len(thesis_words) < thresholds.SPECIFIC_MIN_WORDS:
        return _result(
            "thesis_specific", False,
            f"{len(thesis_words)} words is too thin to be specific",
            span=inp.span_of(inp.thesis),
        )
    if len(concrete) < 2:
        return _result(
            "thesis_specific", False,
            "leans on general words (" +
            ", ".join(sorted(content & _VAGUE_NOUNS)) + ") with little "
            "concrete detail",
            span=inp.span_of(inp.thesis),
        )
    return _result(
        "thesis_specific", True,
        f"names something concrete ({len(concrete)} specific content words)",
        span=inp.span_of(inp.thesis),
    )


def check_thesis_one_sentence(inp: CheckInput) -> ItemResult:
    found = inp.sentences
    if len(found) > 1:
        return _result(
            "thesis_one_sentence", False,
            f"{len(found)} sentences; a tier-1 thesis is one",
            span=inp.span_of(found[1]),
        )
    cap = inp.context.word_cap
    if cap is not None and inp.student_word_count > cap:
        return _result(
            "thesis_one_sentence", False,
            f"{inp.student_word_count} words against a {cap}-word cap",
        )
    return _result("thesis_one_sentence", True, "one sentence")


def check_thesis_separate_from_argument(inp: CheckInput) -> ItemResult:
    """Tier 2 and up: the thesis is its own sentence, not a run-on.

    `thesis_one_sentence` measures the whole response and is only meaningful at
    tier 1, where the whole response *is* the thesis. From tier 2 on, a
    multi-sentence response is the assignment, so this criterion is a different
    one with a different item id rather than the same id quietly changing
    meaning. Carrying the tier-1 id forward would make a met-rate that spans a
    tier change a lie.
    """
    found = inp.sentences
    if len(found) < 2:
        return _result(
            "thesis_separate_from_argument", False,
            "everything is in one sentence, so the thesis and the argument "
            "are not separated",
            span=inp.span_of(inp.thesis),
        )
    thesis_words = len(_words(inp.thesis))
    if thesis_words > 30:
        return _result(
            "thesis_separate_from_argument", False,
            f"the opening sentence runs to {thesis_words} words; the thesis is "
            "carrying the argument inside it",
            span=inp.span_of(inp.thesis),
        )
    return _result("thesis_separate_from_argument", True,
                   f"the thesis is a {thesis_words}-word sentence of its own",
                   span=inp.span_of(inp.thesis))


def check_argument_stated(inp: CheckInput) -> ItemResult:
    rest = inp.after_thesis
    if not rest.strip():
        return _result("argument_stated", False,
                       "nothing follows the thesis, so no argument is stated")
    marker = _contains_any(rest, ("because", "since", "the reason",
                                  "this is why", "so that", "which is why"))
    if marker:
        return _result("argument_stated", True,
                       f"gives a reason (\"{marker}\")",
                       span=inp.span_of(rest))
    if len(_content_words(rest)) >= 3:
        return _result(
            "argument_stated", True,
            "states a supporting idea after the thesis",
            span=inp.span_of(rest),
        )
    return _result("argument_stated", False,
                   "what follows the thesis is too thin to be an argument",
                   span=inp.span_of(rest))


def check_argument_matches_thesis(inp: CheckInput) -> ItemResult:
    thesis_words = _content_words(inp.thesis)
    argument_words = _content_words(inp.after_thesis)
    if not argument_words:
        return _result("argument_matches_thesis", False,
                       "no argument to compare against the thesis")
    share = _share_present(thesis_words, argument_words)
    met = share >= thresholds.ON_THESIS_OVERLAP
    return _result(
        "argument_matches_thesis", met,
        f"the argument shares {share:.0%} of the thesis's key words"
        + ("" if met else ", so it is arguing something else"),
        span=inp.span_of(inp.after_thesis),
    )


def check_evidence_present(inp: CheckInput) -> ItemResult:
    if inp.quoted_text.strip():
        return _result("evidence_present", True, "quotes the passage",
                       span=inp.evidence_span)
    if '"' in inp.scored_text:
        return _result(
            "evidence_present", True,
            "uses quotation marks, though the quoted words do not match the "
            "assigned passage",
            span=inp.evidence_span,
            needs_judgment=True,
        )
    return _result("evidence_present", False, "no evidence from the passage")


def check_evidence_relevant(inp: CheckInput) -> ItemResult:
    evidence_words = _content_words(inp.quoted_text)
    if not evidence_words:
        return _result("evidence_relevant", False, "no evidence to judge",
                       span=inp.evidence_span)
    thesis_words = _content_words(inp.thesis)
    share = _share_present(thesis_words, evidence_words)
    span = inp.evidence_span
    if share >= thresholds.ON_THESIS_OVERLAP:
        return _result(
            "evidence_relevant", True,
            f"the quotation shares {share:.0%} of the thesis's key words",
            span=span,
        )
    # Good writing often quotes without repeating the thesis's nouns. Before
    # calling that irrelevant, check whether the commentary bridges the two:
    # if it shares words with both, the student did the connecting work even
    # though the quotation alone does not show it.
    commentary_words = _content_words(inp.commentary)
    bridges = (_share_present(thesis_words, commentary_words) > 0
               and _share_present(evidence_words, commentary_words) > 0)
    if bridges:
        return _result(
            "evidence_relevant", True,
            "the quotation shares no wording with the thesis, but the "
            "commentary links the two",
            span=span,
        )
    return _result(
        "evidence_relevant", False,
        "the quotation shares no wording with the thesis and nothing connects "
        "them. Needs a human or model read before this counts as settled",
        span=span,
        needs_judgment=True,
    )


def check_evidence_integrated(inp: CheckInput) -> ItemResult:
    quote = inp.quoted_text.strip()
    if not quote:
        return _result("evidence_integrated", False, "no evidence to integrate",
                       span=inp.evidence_span)
    for sentence in inp.sentences:
        if quote[:24] not in sentence:
            continue
        before = sentence.split(quote[:24])[0].strip(' "“')
        if len(_words(before)) >= 3:
            return _result(
                "evidence_integrated", True,
                f"introduces the quotation (\"{before[:40]}\")",
                span=inp.span_of(sentence),
            )
        return _result(
            "evidence_integrated", False,
            "the quotation is dropped in as its own sentence with no signal "
            "phrase leading into it",
                span=inp.span_of(sentence),
        )
    return _result(
        "evidence_integrated", False,
        "the quotation stands apart from the surrounding sentences",
        span=inp.evidence_span,
    )


def check_commentary_connects(inp: CheckInput) -> ItemResult:
    commentary = inp.commentary
    if not commentary.strip():
        return _result("commentary_connects", False,
                       "no commentary follows the evidence")
    thesis_words = _content_words(inp.thesis)
    share = _share_present(thesis_words, _content_words(commentary))
    met = share >= thresholds.ON_THESIS_OVERLAP
    return _result(
        "commentary_connects", met,
        f"the commentary shares {share:.0%} of the claim's key words"
        + ("" if met else ", so it does not tie the evidence back to the claim"),
        span=inp.span_of(commentary),
    )


def check_commentary_beyond_restatement(inp: CheckInput) -> ItemResult:
    commentary = inp.commentary
    if not commentary.strip():
        return _result("commentary_beyond_restatement", False,
                       "no commentary to judge")
    evidence_words = _content_words(inp.quoted_text)
    commentary_words = _content_words(commentary)
    echo = _share_present(commentary_words, evidence_words)
    if evidence_words and echo >= thresholds.COMMENTARY_RESTATEMENT_OVERLAP:
        return _result(
            "commentary_beyond_restatement", False,
            f"{echo:.0%} of the commentary is the quotation's own words, so it "
            "restates the evidence rather than interpreting it",
            span=inp.span_of(commentary),
        )
    marker = _contains_any(commentary, _INTERPRETIVE_MARKERS)
    if marker:
        return _result(
            "commentary_beyond_restatement", True,
            f"reaches past the quotation (\"{marker}\")",
            span=inp.span_of(commentary),
        )
    return _result(
        "commentary_beyond_restatement", False,
        "adds words after the evidence without an interpretive move. Needs a "
        "human or model read before this counts as settled",
        span=inp.span_of(commentary),
        needs_judgment=True,
    )


CHECKS: dict[str, CheckFn] = {
    "answers_prompt": check_answers_prompt,
    "thesis_arguable": check_thesis_arguable,
    "thesis_specific": check_thesis_specific,
    "thesis_one_sentence": check_thesis_one_sentence,
    "thesis_separate_from_argument": check_thesis_separate_from_argument,
    "argument_stated": check_argument_stated,
    "argument_matches_thesis": check_argument_matches_thesis,
    "evidence_present": check_evidence_present,
    "evidence_relevant": check_evidence_relevant,
    "evidence_integrated": check_evidence_integrated,
    "commentary_connects": check_commentary_connects,
    "commentary_beyond_restatement": check_commentary_beyond_restatement,
}


def judge_with_model(question: str, text: str) -> None:
    """STUB. Production scoring prompts are out of scope for the substrate.

    When this lands it must return a verdict plus the span it judged, and it
    must never receive a student handle: the call site passes text and a
    question, which is all a criterion-referenced judgement needs.
    """
    raise NotImplementedError(
        "model-judged scoring is a stub in the substrate; criteria that need "
        "it report needs_judgment=True instead of guessing"
    )


# --- Guards -----------------------------------------------------------------


def assert_criteria_published(published_at: datetime,
                              measured_at: datetime) -> None:
    """Refuse to measure work against criteria that did not exist yet.

    Takes two datetimes and no student handle, so the ingest path can call it
    with a real `submitted_at` without handing this module a person.
    """
    if published_at is None or measured_at is None:
        return
    if published_at > measured_at:
        raise CriteriaNotPublishedError(
            f"criteria published {published_at.isoformat()} postdate the work "
            f"submitted {measured_at.isoformat()}; students cannot be measured "
            "against a checklist they had not been shown"
        )


# --- Entry point ------------------------------------------------------------


def score_submission(
    student_segments: list[Segment],
    criteria_set: CriteriaSet,
    assignment_context: AssignmentContext,
    *,
    submission_id: str = "",
    raw_text: str | None = None,
    now: datetime | None = None,
) -> Score:
    """Score one submission against one published checklist.

    `student_segments` is the student prose plus any legitimately quoted
    source, in document order: see `Submission.segments_for_scoring`.
    Assignment and scaffold text arrives through `assignment_context` as
    labeled provided text, so a check can ask whether a thesis answers the
    prompt without mistaking the prompt for the answer.
    """
    if criteria_set.published_at is not None:
        published = criteria_set.published_at.date()
        if published > assignment_context.date:
            raise CriteriaNotPublishedError(
                f"criteria {criteria_set.criteria_set_id} published "
                f"{published.isoformat()} postdate rep "
                f"{assignment_context.rep_id} on "
                f"{assignment_context.date.isoformat()}"
            )

    student_text = " ".join(s.text.strip() for s in student_segments
                           if s.origin == "student" and s.text.strip())
    quoted_text = " ".join(s.text.strip() for s in student_segments
                           if s.origin == "quoted_source" and s.text.strip())
    scored_segments = [s for s in student_segments if s.text.strip()]
    scored_text = " ".join(s.text.strip() for s in scored_segments)
    span_text = raw_text if raw_text is not None else scored_text
    scored_offsets: list[int] | None = None
    if raw_text is not None:
        # The scorer excludes supplied segments, but a span may bridge across
        # one. Map every scorer character to its original raw position so the
        # stored slice keeps any intervening raw text rather than persisting a
        # reconstructed version of the student's submission.
        scored_offsets = []
        for index, segment in enumerate(scored_segments):
            stripped = segment.text.strip()
            leading = len(segment.text) - len(segment.text.lstrip())
            if index:
                scored_offsets.append(segment.span_start + leading - 1)
            scored_offsets.extend(range(segment.span_start + leading,
                                        segment.span_start + leading
                                        + len(stripped)))
    provided_text = "\n".join(
        [assignment_context.prompt_text]
        + [b.template for b in assignment_context.scaffold_blocks]
    )
    student_word_count = len(_words(student_text))

    stamped = now or utc_now()

    if student_word_count == 0:
        per_item = {
            item.item_id: _result(
                item.item_id, False,
                "not scored: the submission contains no student writing",
            )
            for item in criteria_set.items
        }
        return Score(
            submission_id=submission_id,
            criteria_set_id=criteria_set.criteria_set_id,
            per_item=per_item,
            total=0,
            possible=len(criteria_set.items),
            scored_at=stamped,
            scorer_version=SCORER_VERSION,
            status="no_student_text",
        )

    bundle = CheckInput(
        scored_text=scored_text,
        raw_text=span_text,
        scored_offsets=scored_offsets,
        student_text=student_text,
        quoted_text=quoted_text,
        provided_text=provided_text,
        context=assignment_context,
        student_word_count=student_word_count,
    )

    per_item: dict[str, ItemResult] = {}
    for item in criteria_set.items:
        check = CHECKS.get(item.check_id)
        if check is None:
            raise UnknownCheckError(
                f"criteria {criteria_set.criteria_set_id} item "
                f"{item.item_id} names check {item.check_id!r}, which this "
                f"scorer ({SCORER_VERSION}) does not implement"
            )
        outcome = check(bundle)
        # A check reports under its own check_id; the Score is keyed by the
        # criterion's item_id so two tiers can share a check.
        per_item[item.item_id] = ItemResult(
            item_id=item.item_id,
            met=outcome.met,
            evidence_span=outcome.evidence_span,
            note=outcome.note,
            needs_judgment=outcome.needs_judgment,
        )

    return Score(
        submission_id=submission_id,
        criteria_set_id=criteria_set.criteria_set_id,
        per_item=per_item,
        total=sum(1 for r in per_item.values() if r.met),
        possible=len(criteria_set.items),
        scored_at=stamped,
        scorer_version=SCORER_VERSION,
    )
