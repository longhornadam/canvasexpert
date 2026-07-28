# Brief — the noticings that never reach the record

**Active execution brief. Written 2026-07-28.** One vertical batch.
Supersedes `CanvasExpert-WritingRecord-DocxIngest-BRIEF.md`, YELLOW and closed at `8960bda`,
execution result recorded at `5b44efa`.

**Read `docs/reference/writing-record-module-map.md` first.** It carries this subsystem's
durable state — invariants, delivered batches, open decisions, known defects, and the
verification discipline. This brief assumes it and does not repeat it.

---

## 1. Objective

When the checker marks a criterion unmet, that noticing reaches the student's record. Today a
share of them are thrown away without a trace: the score says *unmet*, the record holds nothing,
and no flag, count, or log line says a noticing went missing.

## 2. The one hard problem, measured

`observations.observe_submission` records an observation only for an **unmet** item, and only if
`result.evidence_span` is present — INV-3, correctly, refuses a verdict nobody can quote
(`core/observations.py:278`). But `_span_of` (`core/scoring.py:135`) is an exact
`scored_text.find(fragment)`, and several checks hand it a fragment they *rebuilt* by rejoining
sentences with `" ".join(...)`. A rebuilt string is not always a substring of the text it came
from, so the span comes back `None`, and the noticing is dropped.

Measured on a real tier-4 rep through the real scorer — one paragraph, ordinary text, nothing
exotic:

| | items with a verdict but no locatable span | unmet items dropped for want of a span |
|---|---|---|
| single paragraph | 3 of 11 (`evidence_present`, `evidence_relevant`, `evidence_integrated`) | **2 of 3** |
| two paragraphs, commentary straddling the break | 7 of 11 (adds `argument_stated`, `argument_matches_thesis`, `commentary_beyond_restatement`, `commentary_connects`) | 2 of 3 |

**The route card is wrong where it calls this latent, and its entry needs replacing, not
extending.** It describes one mechanism — `" ".join` reconstruction versus the `"\n\n"` a
submission stores — and concludes the defect cannot fire because daily reps are single-paragraph
and ECRs are unscored. There is a second mechanism it does not mention, and that one fires on
single-paragraph reps *today*: the evidence family loses its span on ordinary text with a
quotation in it. Two of three unmet criteria on the rep above never reached the record.

Reproduce before changing anything. Tier 4, a rep dated after the criteria publication date
(`tier4_commentary.v1` is published 2026-10-20, which is why a fixture dated September raises
`CriteriaNotPublishedError`), segments from `segment_submission`, filtered to
`origin in ("student", "quoted_source")`, through `score_submission`. Then print each item's
`met` and whether `evidence_span` is None. The two texts that produced the table:

```
Phones should stay in backpacks during class. The article says "test scores fell
twelve percent in classrooms that allowed phones," which is a big drop. That
number matters because it shows the distraction costs real learning. It connects
back to why the rule should change.
```

and the same text with `\n\n` before "That number matters".

## 3. Locked decisions

1. **INV-3 stands.** No observation without a real, quoted, scrubbed span. The fix is to make the
   span locatable, never to relax what an observation must carry.
2. **A stored span stays an exact substring of the text it reports offsets into.** Whatever
   normalisation helps *find* a fragment, what gets stored is real text at real offsets. A
   normalised or reconstructed string must never be persisted as evidence — `Span` is used to
   quote back to a teacher and a student.
3. **A drop must stop being silent.** If a check reaches a verdict whose evidence cannot be
   located, that is a defect signal. It gets surfaced where someone will see it. Deciding *how*
   is yours (§5.2), but "log it and move on" is not an answer: nothing reads the log.
4. **No scoring semantics change.** An item that was unmet stays unmet, and no check changes what
   it considers thesis, evidence, or commentary. This batch changes where a span comes from and
   what happens when there is not one. If a fix requires changing a verdict, that is a YELLOW.
5. **No ECR scoring.** Extended pieces stay unscored. That is the next open question, not this
   one, and it needs the live run first (§9).

## 4. Scope and insertion points

| Change | File | Note |
|---|---|---|
| Span location | `api/dailywriting/core/scoring.py` | `_span_of` :135 and every caller that passes a rebuilt fragment. `CheckInput.after_thesis` :173 and `commentary` :177 are the rebuilders; `scored_text` is itself `" ".join`ed and per-segment stripped (:560-565), so offsets are relative to that string, not to `raw_text`. Confirm which of the two the callers actually need. |
| Drop visibility | `api/dailywriting/core/scoring.py` or `core/observations.py` | Wherever the decision in §5.2 lands. |
| Flag vocabulary, if that is the choice | `api/dailywriting/core/models.py`, `core/digest.py` | A new `SegmentationFlag` code is a `Literal` plus a digest surfacing decision. The `unscrubbed_name_removed` code was removed at `0a9e713`; do not reuse its shape without reading why it went. |

Out of scope: the store and the codec, `projection.py`, `canvas_ingest.py` and
`canvas_attachments.py`, `core/scrub.py`, criteria JSON and `thresholds.py`, `api/mirror/`,
`api/powergrader/`, and the MCP tool surface.

## 5. Decisions to make explicitly and record in §12

1. **Which span the caller wants**: an offset into `scored_text` (what `_span_of` does now) or
   into the submission's `raw_text`. They differ — `scored_text` drops non-student segments and
   collapses per-segment whitespace — and an observation quoted back to a teacher should be
   findable in what the student actually wrote. Say which one every stored span means.
2. **What "not silent" is.** A flag on the submission, a counter on the `Score`, a refusal, or
   something else. Weigh: a flag is visible in the weekly digest but adds vocabulary; a counter
   is cheap but nothing renders it; a refusal is loud but turns a partial result into no result.
3. **Whether the evidence family's loss is the same bug or a second one.** The table above
   suggests two mechanisms. Fix both or say why one is out of reach, and do not assume a single
   root cause because a single patch makes the numbers go to zero.
4. **Whether past records can be repaired.** `cli/score.py` exists to replay a scorer fix over
   stored work (`cli/score.py:5`), and reps are stored precisely so that is possible
   (`store/codec.py:131-135`). State whether a replay recovers the dropped observations, and if
   it does, whether this batch runs one. Nothing is stored on this machine yet, so this is a
   question about the mechanism, not about data.

## 6. Acceptance criteria

1. The single-paragraph rep in §2 produces an observation for **every** unmet item that has a
   pattern tag in `_ITEM_PATTERNS`. The measured 2-of-3 loss goes to zero.
2. The two-paragraph version produces the same observations as the single-paragraph version.
   A paragraph break is not a semantic event.
3. Every stored `Span` satisfies: `text[span.start:span.end] == span.text`, against whichever
   text §5.1 says spans are relative to. Assert it directly, on every span the corpus produces.
4. When a span genuinely cannot be located, the §5.2 signal appears, and a test drives that path
   with a constructed case rather than asserting it never happens.
5. The pinned fixture corpus is unchanged in `student_word_count` and segment origins, and any
   change in per-item verdicts or observation counts is **listed item by item** in §12 with a
   reason. Observation counts are expected to rise; a verdict flipping is a §3.4 violation.
6. Every new assertion is shown failing against `HEAD` before the fix. The route card is explicit
   that a green suite is evidence about the tests.

## 7. Named verification gate

```bash
python -m pytest api/tests/dailywriting api/tests/test_mcp_server_tools.py -q
```

Plus the full `api/tests` suite. On this machine the baseline is **1594 passed, 0 failed**, and
the route card's historical environmental-failure list did not reproduce here — so a failure is
this batch's until proven otherwise. Re-establish it on a clean checkout anyway.

Required in addition: a **before/after corpus snapshot through the scoring path** — per fixture,
each item's `met` and whether it carries a span, plus the observation count. The
segmentation-only snapshot cannot see a scoring change; the DOCX batch learned that and used an
ingest-level snapshot instead (`5b44efa` §12, "Commands and counts").

## 8. Explicit non-goals

- ECR scoring, new criteria, tier changes, `thresholds.py`.
- The `purpose` / genre field. See §9: it is not earned.
- Storing delivered feedback.
- PDF, OCR, handwriting.
- `feedback_scrub.build_replacement_map`'s ignored `protected` parameter — real cruft, four
  production call sites pass it and the body never reads it, but it is PowerGrader-shared and
  belongs to its own change.

## 9. What is left in this subsystem after this batch, and what gates each

Recorded here so the sequence is not re-derived from scratch next time.

1. **Extended pieces are ingested but unscored.** The largest real gap: an essay contributes
   text, a word count, and flag-derived noticings, and nothing else. The measured reason is in
   the route card — checklists written for a one-sentence rep invert on a 446-word essay, with
   the hook scored as the thesis. Two directions: teacher-authored criteria for extended writing,
   or the assistant doing the judging through the MCP surface with CanvasExpert staging the
   result. **Gated on the August live run**: the right answer depends on what real essays and a
   real teacher's reaction look like, and choosing now is guessing.
2. **Delivered feedback is not stored.** Coaching's first question is "what have I already told
   this writer," and the record cannot answer it. Constraints already worked out in the route
   card: written on delivery rather than generation, exemplar pairs held by `submission_id`
   reference and never as embedded text. **Gated on** the FeedbackExpert write-back decision;
   this crosses into PowerGrader's surfaces and should not be planned as a writing-record-only
   batch.
3. **The `purpose` / genre field: recommend closing this as not earned.** The card's argument is
   that a narrative following an argument reads as regression to a reader who cannot see the task
   changed. But `prompt_text` is teacher-authored, never gated by `include_text`, and always
   emitted, so the reader *can* see the task changed. The only real gap is an assignment whose
   Canvas description is empty, and nothing yet says how often that happens. Revisit with a
   measurement from the live run, not before. Nothing in Canvas or in the rubric files carries a
   genre to derive it from — checked: rubrics have `flavor`, `family`, `applies_to`, and no mode.
4. **"Which assignments feed the record": recommend closing this as decided.** Option 1, the
   ingest action is the opt-in, has now shipped twice and needed no mechanism. Leaving it open
   invites someone to build the flag it was decided against.

## 10. Stop conditions

Return YELLOW rather than guessing if: locating a span faithfully requires changing what a check
treats as thesis, evidence, or commentary (that is scoring semantics, §3.4); or if the two
mechanisms in §2 turn out to need incompatible fixes.

Return RED if INV-3 has to bend, if a stored record needs migrating, or if the honest fix lands
in criteria JSON rather than in code.

## 11. References (section-routed; do not read wholesale)

- `docs/reference/writing-record-module-map.md` — **read first**, and correct its known-defect
  entry per §2 as part of this batch.
- `AGENTS.md` — *Non-negotiable guardrails*, *Executor responsibilities*, *Lean engineering defaults*.
- `api/dailywriting/core/scoring.py` — `_span_of` :135, `CheckInput.after_thesis` :173,
  `commentary` :177, `score_submission`'s text assembly :560.
- `api/dailywriting/core/observations.py` — `add` :277 (the drop), `_ITEM_PATTERNS` :66,
  `observe_submission` :300 (unmet items only).
- `api/dailywriting/core/models.py` — `SegmentationFlag` codes, `Span`.
- `api/dailywriting/cli/score.py` — the replay path, for §5.4.
- `docs/reference/project-state.md` — pre-launch, 0 users, live run in August.

## 12. Execution result

**GREEN.** Implementation commit: `634484d1942a35e08d53ab1d34c4c949d1f7f5b2`.

Changed: `core/scoring.py`, `core/ingest.py`, `cli/score.py`, `core/observations.py`,
`core/models.py`, `core/digest.py`, the history-blind signature test, the new focused
`test_dw_evidence_spans.py`, and the Writing Record route card.

### Locked decisions

1. **Every stored `Span` is relative to `Submission.raw_text`.** This is the scrubbed text a
   teacher can actually open. The scorer still reasons only over student and quoted-source
   segments; it now maps the scorer-string match through those segments' raw offsets and stores
   the literal inclusive raw slice. A provided scaffold between two selected segments remains in
   that literal slice rather than being silently omitted or reconstructed.
2. **An unlocatable observation is a submission flag, rendered in the weekly digest.**
   `unlocatable_evidence_span` names the unmet pattern-bearing criterion ids in a private detail
   string. INV-3 still refuses to create the free-floating observation; the teacher sees the
   failure under *Needs human eyes* instead of having to inspect a log.
3. **The two mechanisms were distinct but compatible.** Paragraph/scaffold reconstruction was
   a text-geometry failure, fixed by scorer-to-raw offset mapping and whitespace-tolerant match.
   The evidence family had no span at all for an unknown literal quotation, fixed by using that
   literal quotation as evidence geometry only. It remains an unknown-source quotation, so every
   verdict is unchanged.
4. **A `dailywriting-score` replay alone does not recover old observations.** It now produces
   correct raw-relative score spans, but its append-only path does not re-run or replace
   observations. No local records exist, so this batch did not run it; replaying stored dropped
   observations needs a deliberately scoped observation-rebuild operation later.

### Before/after scoring-path snapshots

Legend: `M` / `U` is met / unmet; `S` / `-` is evidence span present / absent.

The required tier-4 reproduction changed only span availability and the two resulting
observations; no verdict changed.

| Input | Before | After |
|---|---|---|
| single paragraph | `evidence_present=M-`, `evidence_relevant=U-`, `evidence_integrated=U-`; 2 observations | `evidence_present=MS`, `evidence_relevant=US`, `evidence_integrated=US`; 4 observations |
| two paragraphs | `argument_stated=M-`, `argument_matches_thesis=M-`, `evidence_present=M-`, `evidence_relevant=U-`, `evidence_integrated=U-`, `commentary_connects=M-`, `commentary_beyond_restatement=M-`; 2 observations | every item carries `S`; 4 observations, the same four `(criterion, pattern)` pairs as the single paragraph |

Pinned `singles.json` scoring snapshot (before equals after for every row; therefore no changed
verdicts or observation counts):

```text
F1  words=24 origins=student observations=0
    answers_prompt=MS arguable=MS specific=MS one_sentence=M-
F2  words=12 origins=student observations=1
    answers_prompt=MS arguable=US specific=MS one_sentence=M-
F3  words=8 origins=assignment,student observations=1
    answers_prompt=MS arguable=US specific=MS one_sentence=M-
F4  words=13 origins=scaffold,student observations=3
    answers_prompt=US arguable=US specific=MS thesis_separate=US argument_stated=U- argument_matches_thesis=U- evidence_present=U- evidence_relevant=U- evidence_integrated=U- commentary_connects=U- commentary_beyond_restatement=U-
F5  words=0 origins=scaffold observations=1
    answers_prompt=U- arguable=U- specific=U- thesis_separate=U- argument_stated=U- argument_matches_thesis=U- evidence_present=U- evidence_relevant=U- evidence_integrated=U- commentary_connects=U- commentary_beyond_restatement=U-
F6  words=38 origins=quoted_source,student observations=1
    answers_prompt=MS arguable=MS specific=MS thesis_separate=MS argument_stated=MS argument_matches_thesis=MS evidence_present=MS evidence_relevant=US evidence_integrated=MS
F7  words=17 origins=quoted_source,student observations=2
    answers_prompt=MS arguable=US specific=MS thesis_separate=MS argument_stated=MS argument_matches_thesis=MS evidence_present=MS evidence_relevant=MS evidence_integrated=US
F8  words=18 origins=student observations=0
    answers_prompt=MS arguable=MS specific=MS one_sentence=M-
F12 words=60 origins=quoted_source,scaffold,student observations=2
    answers_prompt=MS arguable=MS specific=MS thesis_separate=MS argument_stated=MS argument_matches_thesis=MS evidence_present=MS evidence_relevant=US evidence_integrated=MS commentary_connects=MS commentary_beyond_restatement=MS
```

The source values for `student_word_count` and segment origins were also compared before/after
for every fixture above; all are identical. The focused corpus test asserts every present span is
an exact `raw_text[start:end]` slice. It failed on pre-fix `HEAD` at F3 / `answers_prompt`.

### Commands and counts

- Detached clean-checkout baseline: `python -m pytest api/tests -q` — **1594 passed** in 82.12s.
- New focused assertions before the fix: `python -m pytest api/tests/dailywriting/test_dw_evidence_spans.py -q` — **2 failed** (the two dropped evidence observations and absent visibility flag).
- Raw-slice corpus assertion against pre-fix `HEAD` — failed at **F3 / `answers_prompt`**.
- Named gate: `python -m pytest api/tests/dailywriting api/tests/test_mcp_server_tools.py -q` — **242 passed** in 30.16s.
- Full API suite: `python -m pytest api/tests -q` — **1597 passed** in 81.55s.

No deviations from the locked scope and no unresolved decisions.
