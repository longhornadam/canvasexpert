"""Attribute each stretch of a submission to who wrote it.

This is not primarily a classification problem. The system already holds the
exact prompt text and the exact scaffold templates from authoring time, so the
job is alignment: locate and mask the known-provided text, and treat the
residue as student-authored. A classifier only earns a say over what alignment
could not explain, and even then it flags rather than decides.

Stages run in order and first match wins:

  1. exact match against prompt, scaffold literals, and boilerplate
  2. fuzzy match against the same corpus, catching reworded restatement
  3. stem alignment, the important one, because stems are designed to be
     completed and the interior of a completed stem is the student's writing
  4. quoted-source detection, which is a different origin from scaffold
  5. mid-prompt fragment detection, gated to long responses only: a short
     verbatim run lifted out of the *middle* of the prompt and buried inside
     otherwise-original writing, which stage 1/2's whole-prompt-length
     matching cannot see (below). Gated because the same shape -- a handful
     of prompt words verbatim, near the start of the response -- is also
     ordinary student use of a question's topic words. Below the length gate,
     this stage does not run at all.
  6. residual, which is the student

Stem alignment is allowed to re-read tokens stage 1 already called `scaffold`,
because confirming the same origin costs nothing and a blanked template's
literal half is exactly what stage 1 matches. It may only claim an *unowned*
token as the blank's fill, so first-match-wins still holds for student prose.

Downstream rules this module exists to make true:

  - Preserve `student` and `quoted_source` as distinct origins so a later
    reader can distinguish supplied text from student prose.
  - `student_word_count` counts `student` segments only.
  - Zero student words is a structural flag, not an evaluation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from api.dailywriting.config import thresholds
from api.dailywriting.core.models import (
    AssignmentContext,
    Origin,
    ScaffoldBlock,
    Segment,
    SegmentationFlag,
    SegmentMethod,
    Span,
)

BLANK_TOKEN = "{{BLANK}}"

# Canvas and template chrome students paste along with their answer.
DEFAULT_BOILERPLATE = (
    "Type your response below.",
    "Type your answer here.",
    "Submit your response below.",
    "Write your answer in the box below.",
    "Delete this line before you submit.",
    "Name:",
    "Date:",
    "Period:",
)

# Length-preserving punctuation normalisation. Every mapping is one character
# to one character, so token offsets in the normalised text are offsets in the
# original text and no offset bookkeeping is needed.
_TRANSLATE = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "−": "-",
    " ": " ", "…": ".", "ʼ": "'", "`": "'",
})

_WORD = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)*")


@dataclass(frozen=True)
class Token:
    start: int
    end: int
    raw: str
    norm: str


@dataclass(frozen=True)
class SegmentationResult:
    segments: list[Segment]
    student_word_count: int
    flags: list[SegmentationFlag] = field(default_factory=list)

    def text_for(self, *origins: Origin) -> str:
        return " ".join(s.text.strip() for s in self.segments
                        if s.origin in origins and s.text.strip())

    @property
    def low_confidence(self) -> bool:
        return any(f.code == "low_confidence_segment" for f in self.flags)


def normalize(text: str) -> str:
    """Length-preserving normalisation. Offsets survive."""
    return (text or "").translate(_TRANSLATE)


def tokenize(text: str) -> list[Token]:
    """Word tokens with original offsets. Punctuation is not a token."""
    normalized = normalize(text)
    return [
        Token(start=m.start(), end=m.end(), raw=m.group(),
              norm=m.group().lower())
        for m in _WORD.finditer(normalized)
    ]


def _norms(tokens: list[Token]) -> list[str]:
    return [t.norm for t in tokens]


def _similarity(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()


def _claimable(owner: list[Origin | None], start: int, end: int,
               allow: tuple[Origin | None, ...] = (None,)) -> bool:
    return all(owner[i] in allow for i in range(start, end))


def _find_exact(hay: list[str], needle: list[str],
                owner: list[Origin | None],
                allow: tuple[Origin | None, ...] = (None,),
                from_index: int = 0) -> tuple[int, int] | None:
    """First unclaimed exact token-subsequence match of `needle` in `hay`."""
    span = len(needle)
    if not span or span > len(hay):
        return None
    for start in range(from_index, len(hay) - span + 1):
        if hay[start:start + span] != needle:
            continue
        if _claimable(owner, start, start + span, allow):
            return start, start + span
    return None


def _find_fuzzy(hay: list[str], needle: list[str],
                owner: list[Origin | None],
                threshold: float,
                allow: tuple[Origin | None, ...] = (None,),
                from_index: int = 0) -> tuple[int, int, float] | None:
    """Best unclaimed window whose similarity to `needle` clears `threshold`.

    Windows are searched at lengths around the needle's own length, which is
    what makes a lightly reworded prompt restatement findable without letting
    a four-word window claim a forty-word prompt.
    """
    span = len(needle)
    if not span or not hay:
        return None
    low = max(1, int(span * 0.75))
    high = min(len(hay), int(span * 1.25) + 1)
    best: tuple[int, int, float] | None = None
    for width in range(low, high + 1):
        for start in range(from_index, len(hay) - width + 1):
            if not _claimable(owner, start, start + width, allow):
                continue
            score = _similarity(hay[start:start + width], needle)
            if score >= threshold and (best is None or score > best[2]):
                best = (start, start + width, score)
    return best


def _claim(owner: list[Origin | None], methods: list[SegmentMethod | None],
           confidences: list[float], start: int, end: int,
           origin: Origin, method: SegmentMethod, confidence: float) -> None:
    for i in range(start, end):
        if owner[i] is None:
            owner[i] = origin
            methods[i] = method
            confidences[i] = confidence


def _scaffold_literals(block: ScaffoldBlock) -> list[str]:
    """Literal parts of a template, split on the blank marker."""
    return block.template.split(BLANK_TOKEN)


def _align_stem(
    tokens: list[Token],
    block: ScaffoldBlock,
    owner: list[Origin | None],
    methods: list[SegmentMethod | None],
    confidences: list[float],
    flags: list[SegmentationFlag],
    text: str,
) -> bool:
    """Align one blanked template, marking literals scaffold and fills student.

    Returns True if the template's literal skeleton was found. Multi-blank
    templates align piecewise, left to right.
    """
    literals = _scaffold_literals(block)
    if len(literals) < 2:
        return False

    hay = _norms(tokens)
    literal_allow: tuple[Origin | None, ...] = (None, "scaffold")
    cursor = 0
    placed: list[tuple[int, int]] = []  # literal token ranges, in order
    found_any = False

    for literal in literals:
        needle = _norms(tokenize(literal))
        if len(needle) < thresholds.STEM_MIN_LITERAL_TOKENS:
            # Too short to align on. Record a zero-width anchor at the cursor
            # so the surrounding blanks still bound correctly.
            placed.append((cursor, cursor))
            continue
        hit = _find_exact(hay, needle, owner, literal_allow, cursor)
        confidence = 1.0
        method: SegmentMethod = "stem_align"
        if hit is None:
            fuzzy = _find_fuzzy(hay, needle, owner,
                                thresholds.FUZZY_MATCH_THRESHOLD,
                                literal_allow, cursor)
            if fuzzy is None:
                placed.append((cursor, cursor))
                continue
            hit = (fuzzy[0], fuzzy[1])
            confidence = fuzzy[2]
        found_any = True
        _claim(owner, methods, confidences, hit[0], hit[1],
               "scaffold", method, confidence)
        placed.append(hit)
        cursor = hit[1]

    if not found_any:
        return False

    # Everything between consecutive literals is a blank's fill. A trailing
    # blank runs to the end of the text, which is the ordinary shape of a
    # sentence stem.
    for index in range(len(placed) - 1):
        fill_start = placed[index][1]
        fill_end = placed[index + 1][0]
        if index + 1 == len(placed) - 1 and not literals[-1].strip():
            fill_end = len(tokens)
        _claim_fill(tokens, owner, methods, confidences, flags,
                    fill_start, fill_end, block, text)

    return True


def _claim_fill(tokens: list[Token], owner: list[Origin | None],
                methods: list[SegmentMethod | None], confidences: list[float],
                flags: list[SegmentationFlag], start: int, end: int,
                block: ScaffoldBlock, text: str) -> None:
    """Claim a stem's blank interior as student prose, or flag an empty blank."""
    claimable = [i for i in range(max(0, start), min(end, len(tokens)))
                 if owner[i] is None]
    if not claimable:
        flags.append(SegmentationFlag(
            code="empty_stem_blank",
            detail=(f"scaffold {block.block_id} was submitted with an empty "
                    "blank: the stem is present and the student contributed "
                    "nothing to it"),
            span=Span(
                start=tokens[start - 1].start if 0 < start <= len(tokens) else 0,
                end=tokens[start - 1].end if 0 < start <= len(tokens) else 0,
                text=block.template,
            ),
        ))
        return
    _claim(owner, methods, confidences, claimable[0], claimable[-1] + 1,
           "student", "stem_align", 1.0)


def _coalesce(text: str, tokens: list[Token], owner: list[Origin | None],
              methods: list[SegmentMethod | None],
              confidences: list[float]) -> list[Segment]:
    """Group runs of same-origin tokens into segments that tile the text.

    A segment's span runs to the start of the next segment, so punctuation and
    whitespace attach to the preceding segment. That matters: the
    one-sentence check needs to see the period.
    """
    if not tokens:
        return []

    groups: list[tuple[int, int]] = []
    for index in range(len(tokens)):
        same = (groups and
                owner[groups[-1][0]] == owner[index] and
                methods[groups[-1][0]] == methods[index] and
                abs(confidences[groups[-1][0]] - confidences[index]) < 1e-9)
        if same:
            groups[-1] = (groups[-1][0], index + 1)
        else:
            groups.append((index, index + 1))

    segments: list[Segment] = []
    for position, (first, last) in enumerate(groups):
        span_start = 0 if position == 0 else tokens[groups[position][0]].start
        if position == 0:
            span_start = 0
        span_end = (len(text) if position == len(groups) - 1
                    else tokens[groups[position + 1][0]].start)
        # `owner[first]` is never None here: stage 6 relabels every unclaimed
        # token `student` before `_coalesce` runs, which is what makes
        # `Origin`'s vocabulary exactly the four values `Segment` can hold.
        origin = owner[first]
        segments.append(Segment(
            span_start=span_start,
            span_end=span_end,
            text=text[span_start:span_end],
            origin=origin,
            confidence=confidences[first],
            method=methods[first] or "residual",
        ))
    return segments


def segment_submission(
    text: str,
    context: AssignmentContext,
    *,
    boilerplate: tuple[str, ...] = DEFAULT_BOILERPLATE,
    fuzzy_threshold: float | None = None,
    quoted_threshold: float | None = None,
) -> SegmentationResult:
    """Attribute `text` against everything the authoring record knows.

    `text` must already be scrubbed: see `core.scrub.scrub_writing`. Offsets in
    the returned segments are offsets into `text` as given.
    """
    fuzzy_threshold = (thresholds.FUZZY_MATCH_THRESHOLD
                       if fuzzy_threshold is None else fuzzy_threshold)
    quoted_threshold = (thresholds.QUOTED_SOURCE_THRESHOLD
                        if quoted_threshold is None else quoted_threshold)

    text = normalize(text or "")
    tokens = tokenize(text)
    flags: list[SegmentationFlag] = []

    if not tokens:
        return SegmentationResult(segments=[], student_word_count=0, flags=[
            SegmentationFlag(code="no_student_text",
                             detail="the submission contains no words"),
        ])

    owner: list[Origin | None] = [None] * len(tokens)
    methods: list[SegmentMethod | None] = [None] * len(tokens)
    confidences: list[float] = [0.0] * len(tokens)
    hay = _norms(tokens)

    plain_blocks = [b for b in context.scaffold_blocks
                    if BLANK_TOKEN not in b.template]
    blank_blocks = [b for b in context.scaffold_blocks
                    if BLANK_TOKEN in b.template]

    # A blanked template's literal half is legitimate provided text, so stage 1
    # sees it with the marker stripped out, exactly as the handoff specifies.
    corpus: list[tuple[str, Origin]] = [(context.prompt_text, "assignment")]
    corpus += [(b.template, "scaffold") for b in plain_blocks]
    corpus += [(b.template.replace(BLANK_TOKEN, " "), "scaffold")
               for b in blank_blocks]
    corpus += [(chunk, "assignment") for chunk in boilerplate]

    # Stage 1: exact.
    for provided, origin in corpus:
        needle = _norms(tokenize(provided))
        hit = _find_exact(hay, needle, owner)
        if hit:
            _claim(owner, methods, confidences, hit[0], hit[1],
                   origin, "exact_match", 1.0)

    # Stage 2: fuzzy.
    for provided, origin in corpus:
        needle = _norms(tokenize(provided))
        hit = _find_fuzzy(hay, needle, owner, fuzzy_threshold)
        if hit:
            _claim(owner, methods, confidences, hit[0], hit[1],
                   origin, "fuzzy_match", round(hit[2], 4))

    # Stage 3: stem alignment.
    for block in blank_blocks:
        _align_stem(tokens, block, owner, methods, confidences, flags, text)

    # Stage 4: quoted source. It stays distinct from scaffold and out of the
    # student word count while remaining visible to a later reader.
    for source in context.source_texts:
        needle = _norms(tokenize(source))
        if not needle:
            continue
        hit = _find_exact(hay, needle, owner)
        if hit:
            _claim(owner, methods, confidences, hit[0], hit[1],
                   "quoted_source", "exact_match", 1.0)
            continue
        fuzzy = _find_fuzzy(hay, needle, owner, quoted_threshold)
        if fuzzy:
            _claim(owner, methods, confidences, fuzzy[0], fuzzy[1],
                   "quoted_source", "fuzzy_match", round(fuzzy[2], 4))
            continue
        # A short quotation lifted out of a long passage: look for the longest
        # run of submission tokens that appears verbatim inside the source.
        _claim_embedded_quote(text, tokens, hay, needle, owner, methods,
                              confidences)

    # Stage 5: mid-prompt fragment. Claims only what stage 1/2 could not,
    # because both are already-run and first-match-wins: a whole-prompt copy
    # or reword is claimed there. This stage exists for the shape neither can
    # see -- a short run lifted out of the *middle* of the prompt, buried
    # inside an otherwise-original response -- and reuses the same alignment
    # `_claim_embedded_quote` already does for a quoted source passage. Gated
    # to responses at or above `thresholds.MID_PROMPT_FRAGMENT_MIN_RESPONSE_TOKENS`
    # (see its own comment): below that length this stage does not run at all,
    # so a short rep's opening thesis is never a candidate for it in the first
    # place, regardless of how much it happens to echo the prompt.
    if len(tokens) >= thresholds.MID_PROMPT_FRAGMENT_MIN_RESPONSE_TOKENS:
        prompt_needle = _norms(tokenize(context.prompt_text))
        if prompt_needle:
            _claim_embedded_quote(text, tokens, hay, prompt_needle, owner,
                                  methods, confidences, origin="assignment")

    # Stage 6: residual is the student.
    for index in range(len(tokens)):
        if owner[index] is None:
            owner[index] = "student"
            methods[index] = "residual"
            confidences[index] = 1.0

    segments = _coalesce(text, tokens, owner, methods, confidences)
    student_words = sum(1 for index in range(len(tokens))
                        if owner[index] == "student")

    if student_words == 0:
        flags.append(SegmentationFlag(
            code="no_student_text",
            detail=("every word in this submission matches provided text; "
                    "not evaluated; this is usually a copy-paste error "
                    "rather than a refusal"),
        ))
    if context.word_cap is not None and student_words > context.word_cap:
        flags.append(SegmentationFlag(
            code="exceeds_word_cap",
            detail=f"{student_words} student words against a cap of "
                   f"{context.word_cap}",
        ))
    for segment in segments:
        if (segment.origin != "student"
                and segment.confidence < thresholds.LOW_CONFIDENCE_SEGMENT):
            flags.append(SegmentationFlag(
                code="low_confidence_segment",
                detail=(f"{segment.origin} attributed by {segment.method} at "
                        f"confidence {segment.confidence:.2f}; a human should "
                        "confirm before this steers anything"),
                span=Span(segment.span_start, segment.span_end, segment.text),
            ))

    return SegmentationResult(segments=segments,
                              student_word_count=student_words,
                              flags=flags)


def _claim_embedded_quote(text: str, tokens: list[Token], hay: list[str],
                          needle: list[str], owner: list[Origin | None],
                          methods: list[SegmentMethod | None],
                          confidences: list[float],
                          origin: Origin = "quoted_source") -> None:
    """Claim the run of submission tokens lifted verbatim from `needle`.

    A common case: a student quotes one line out of a source
    paragraph (`origin="quoted_source"`, the default). Stage 5 below reuses
    this same alignment for a short run lifted out of the middle of the
    *prompt* instead (`origin="assignment"`): stage 1/2 already handle a
    whole-prompt copy or a whole-prompt reword, but both pin their window
    widths to the full prompt's own token length, so a five-word fragment
    buried three paragraphs into a long response is never even considered as
    a window. The alignment problem is identical either way -- find the
    longest unclaimed run that appears verbatim inside the source text -- so
    only the origin it is claimed under differs.

    A run that starts just after a quotation mark wins over a longer run that
    does not, because otherwise the student's own signal phrase gets absorbed
    into the quotation whenever it happens to echo the source, and words they
    did write stop counting as theirs.
    """
    source_joined = " " + " ".join(needle) + " "
    best: tuple[int, int, int] | None = None  # (opens_quote, length, start)
    for start in range(len(hay)):
        if owner[start] is not None:
            continue
        char_before = text[tokens[start].start - 1] if tokens[start].start else ""
        opens_quote = 1 if char_before in '"“' else 0
        for end in range(start + thresholds.EMBEDDED_QUOTE_MIN_TOKENS,
                         len(hay) + 1):
            if any(owner[i] is not None for i in range(start, end)):
                break
            window = " " + " ".join(hay[start:end]) + " "
            if window not in source_joined:
                break
            candidate = (opens_quote, end - start, start)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
    if best:
        opens_quote, length, start = best
        _claim(owner, methods, confidences, start, start + length,
               origin, "exact_match", 1.0)


def flag_cross_submission_repetition(
    submissions: dict[str, str],
    *,
    min_students: int | None = None,
    min_tokens: int | None = None,
) -> dict[str, list[SegmentationFlag]]:
    """Find residual text repeated across students on the same rep.

    Cross-submission repetition is a strong signal of provided text the
    authoring record missed. It never changes an origin: it produces a flag
    so a low-confidence classification is visible without becoming an
    evaluation.

    `submissions` maps submission_id to that submission's residual student
    text. Returns flags per submission_id.
    """
    min_students = (thresholds.CROSS_SUBMISSION_REPEAT_MIN_STUDENTS
                    if min_students is None else min_students)
    min_tokens = (thresholds.CROSS_SUBMISSION_REPEAT_MIN_TOKENS
                  if min_tokens is None else min_tokens)

    shingles: dict[tuple[str, ...], set[str]] = {}
    per_submission: dict[str, list[Token]] = {}
    for submission_id, text in submissions.items():
        tokens = tokenize(text or "")
        per_submission[submission_id] = tokens
        norms = _norms(tokens)
        for start in range(0, max(0, len(norms) - min_tokens + 1)):
            key = tuple(norms[start:start + min_tokens])
            shingles.setdefault(key, set()).add(submission_id)

    shared = {key: owners for key, owners in shingles.items()
              if len(owners) >= min_students}
    result: dict[str, list[SegmentationFlag]] = {}
    for key, owners in shared.items():
        phrase = " ".join(key)
        for submission_id in sorted(owners):
            result.setdefault(submission_id, []).append(SegmentationFlag(
                code="cross_submission_repeat",
                detail=(f"{len(owners)} students used the same "
                        f"{min_tokens}-word run on this rep: {phrase!r}. "
                        "Probably provided text the authoring record missed."),
            ))
    return result
