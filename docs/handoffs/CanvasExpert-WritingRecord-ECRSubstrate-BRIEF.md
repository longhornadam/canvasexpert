# Brief — Substrate support for extended writing in the longitudinal record

**Active execution brief. Written 2026-07-28.** One vertical batch, substrate only.
Acquisition (getting ECR text out of Canvas) is explicitly **not** in scope — see §7 and §9.

Supersedes `CanvasExpert-WritingRecord-AssistantRead-BRIEF.md`, which is GREEN and closed.

---

## 1. Objective

The writing record can hold a student's extended writing — a 400–1500 word essay — as an
ordinary `Submission`, so the assistant coaches on a student's whole body of work rather
than only their daily reps.

Batch 1 built the read path: `get_writing_history` projects the record to a connected
assistant. But the store only ever receives daily reps, because `core.ingest.ingest()`
requires a `CriteriaSet` and always scores. This batch makes the substrate accept a long
piece honestly — ingested, segmented, and readable, without pretending a checklist written
for one-sentence reps can grade an essay.

## 2. Why substrate only

The teacher's students submit extended writing three ways: **typed into Canvas, uploaded as
DOCX, and handwritten then OCR-scanned.** Each needs a different acquisition path, and one
of them is not currently possible at all:

- Typed text-entry is already in the mirror as `body` and already pseudonymized and scrubbed
  by `get_submissions`.
- **Uploaded DOCX is invisible to the mirror by construction.** `api/mirror/store.py:583`
  captures `attachment_names` only — filenames, never bytes, never a signed URL — and Canvas
  leaves `body` empty for `online_upload`. Reaching that text needs a live per-submission
  Canvas call, which nothing in the writing record does today.
- OCR is a third pipeline again, and its output is noisy in ways that matter (§8.2).

Bundling acquisition into this batch would make it an architecture batch touching live
Canvas calls, attachment download, and scrub-before-store — exactly the shape the §8.1
decision in the previous brief removed. **Acquisition is Batch 4.** This batch makes sure
that when the text arrives, the substrate handles it correctly.

## 3. Locked decisions

1. **An ECR is ingested but NOT checklist-scored.** Carried forward from the previous
   brief §8.1a, where it is recorded with the measurement behind it. `Score` is absent;
   `projection.py` already emits `total`/`possible`/`status` as null when `score is None`.
2. **Add a second entry point, do not make `criteria_set` optional on `ingest()`.**
   `IngestResult.score` is a required field and four consumers read it. Threading `None`
   through them to serve one new case is worse than a sibling function that shares a private
   scrub-and-segment helper. Do not abstract further than those two callers need.
3. **Flag-derived observations still apply to an unscored piece.** `no_student_text` and
   `exceeds_word_cap` come from segmentation flags, not from criteria, and are worth keeping.
   Criteria-derived observations do not exist without a score and must not be faked.
4. **Prompt-fragment detection is exact-substring only in this batch.** OCR tolerance is
   deliberately deferred — no OCR text is in the store yet, fuzzy matching is the measured
   cost centre (§8.1), and building tolerance for data that does not exist is speculative.
   Revisit in Batch 4, where OCR text first has a consumer.
5. **No performance work.** See §8.1. Measured, and the obvious optimisation does not work.
6. **Nothing in this batch calls Canvas, and nothing writes to `For AI/`.**

## 4. Scope and insertion points

| Change | File | Note |
|---|---|---|
| Unscored ingest entry point | `api/dailywriting/core/ingest.py` | `ingest()` is at :51; scoring at :105. Extract the scrub → segment → `Submission` construction (:76-103) into a private helper and call it from both. The unscored path returns submission + flags + flag-derived observations, no `Score`. |
| Prompt-fragment segmentation | `api/dailywriting/core/segmentation.py` | Insert a new stage **after stage 4 (ends :405) and before stage 5 (:407)**. That position claims only what would otherwise fall through to `student`, so scaffold, stem-alignment, and quoted-source precedence are all untouched. Model it on `_claim_embedded_quote` (:447), which already solves this exact problem for `source_texts`. |
| Product guide — long-piece truncation | `api/mcp_server/tools.py` `_GUIDE_FILES` topic `writing_record` + `api/default_docs/AI Authoring/Writing Record (longitudinal writing history).txt` | Text only. One canonical source, served verbatim. |
| Dead `Origin` value | `api/dailywriting/core/models.py:21`, `segmentation.py:307` | Optional cleanup, see §5.6. Drop it if `codec` round-tripping or a test turns out to depend on the value. |

Out of scope in these files: any change to `core/scoring.py`, the criteria JSON, thresholds,
directive evaluation, the store, the codec, or `projection.py`.

## 5. Acceptance criteria

Each is independently checkable without reading the implementation.

1. A 900-word multi-paragraph submission ingests through the unscored path and produces a
   `Submission` with correct `student_word_count`, no `Score`, and no criteria-derived
   observations. No exception, and no `CriteriaSet` supplied.
2. `Repository.append_submission` stores it and `get_writing_history` returns it with
   `total`, `possible`, and `status` all `null` — asserted end to end, not by unit-testing
   the projection alone.
3. The existing scored path is byte-for-byte unchanged: every current test in
   `api/tests/dailywriting/` passes untouched, and `IngestResult.score` is still a required,
   non-`None` field for it.
4. A verbatim run of ≥ `EMBEDDED_QUOTE_MIN_TOKENS` tokens lifted from the **middle** of
   `prompt_text` and buried three paragraphs into a long response is attributed `assignment`,
   not `student`, and does **not** count toward `student_word_count`. There is no current
   test for this — `test_dw_segmentation.py` covers only a full verbatim prompt copy.
5. Fixture 3's full-prompt-copy behaviour is unchanged (`test_dw_segmentation.py:18` and
   `:28`), and `test_segments_tile_the_whole_text` (`:84`) still passes: segments must still
   tile the text with no gap or overlap.
6. If the dead `unknown` origin is removed, `Origin` no longer advertises a value that
   `segment_submission` cannot produce, and no stored record round-trips through it.
   Stage 5 (`segmentation.py:407-412`) unconditionally relabels every unclaimed token
   `student`, which is what makes the value unreachable.
7. The `writing_record` guide topic states that a long piece is truncated at
   `max_text_chars`, that `student_word_count` reveals how much was not shown, and that the
   caller should raise `max_text_chars` deliberately when reading extended writing. Its text
   is the same bytes as the served file.

## 6. Named verification gate

```bash
python -m pytest api/tests/dailywriting api/tests/test_mcp_server_tools.py -q
```

Plus the full `api/tests` suite for regression. Three tests fail environmentally and are
**not** caused by this work: two Windows long-path failures in `test_feedback_pipeline.py`
and `test_powergrader_packet.py`, plus the load-sensitive
`test_beta075_storage.py::test_spawned_vault_writers_preserve_both_students`, which appears
only under full-suite contention. Confirm against a stashed tree before investigating.

Proportional manual check: none. This batch renders no UI.

## 7. Explicit non-goals

- **No acquisition.** No Canvas call, no attachment download, no DOCX extraction, no OCR.
  That is Batch 4 and it is the larger half of the problem.
- **No `AssignmentContext` construction from a Canvas assignment.** Nothing in the repo does
  this today; it belongs with acquisition.
- **No scoring change.** Not the thesis heuristic, not the paragraph-break span defect
  (recorded in the previous brief §8.1b), not a tier-5 criteria set.
- **No performance work** (§8.1).
- **No OCR-tolerant matching** (§3.4).
- **No teacher-facing report**, no Writing Timeline coupling, no pseudonym format change.

## 8. Measured findings this batch must not relitigate

### 8.1 Segmentation performance — measured, and the obvious fix does not work

Baseline on `rep_t3_forest` (tier 3, one source passage), real `segment_submission`:

| words | time | per word |
|---|---|---|
| 96 | 789 ms | 8.22 ms |
| 288 | 3,100 ms | 10.76 ms |
| 576 | 7,475 ms | 12.98 ms |

Cost is dominated by `_find_fuzzy` (:145), whose inner loop runs `_similarity` over
O(needle length × text length) windows per corpus item, and `_similarity` (:118) rebuilds
`SequenceMatcher` on every call.

**Reusing one `SequenceMatcher` via `set_seq2` was implemented and measured: 0.83x / 0.91x /
1.05x — no win, slower at small sizes.** Segments were byte-identical, so the rewrite was
correct; the hypothesis was wrong. The cost is in `ratio()` computing matching blocks, not in
the constructor. **Do not re-attempt this.**

At ~13 ms/word a 30-student ECR assignment costs roughly four minutes of one-time batch
compute. Nothing has been bitten by that. Any future attempt must be algorithmic — avoiding
the full-text scan per corpus item — and must demonstrate a measured improvement with
identical segmentation output.

### 8.2 OCR degrades pseudonym consistency but does not breach INV-7

Relevant to Batch 4, recorded here so it is not rediscovered. `core/scrub.py` runs two
passes: an exact `\b`-bounded roster pass delegating to `api.feedback_scrub`, then a
heuristic capitalized-token pass for names the roster does not know. An OCR-mangled roster
name ("Marcvs") escapes the first but is still caught by the second and replaced with
`NAME_PLACEHOLDER`. So the name does not leak — but it resolves to `[name]` rather than that
student's stable pseudonym, and the coach loses the thread that two mentions are the same
person. Expect elevated `unscrubbed_name_removed` flag volume on OCR text.

## 9. Sequenced follow-on batches (not this batch)

- **Batch 4 — ECR acquisition.** Three routes, in ascending cost: typed text-entry (mirror
  already has `body`); DOCX upload (needs a live per-submission Canvas call plus extraction —
  `api/powergrader/student_attachments.py:49` `_docx_segments` already turns DOCX bytes into
  plain text and `python-docx` is a declared dependency); OCR (a third pipeline, plus §8.2).
  Also carries `AssignmentContext` construction from a Canvas assignment, the
  `AssignmentContext` purpose field (previous brief §8a.1), and OCR-tolerant fragment
  matching (§3.4).
- **Batch 5 — pseudonym format and scrub correctness.** Unchanged from the previous brief §9.
  Not time-pressured: the store keys on `canvas_id`, so no on-disk key depends on the
  pseudonym string.
- **Batch 6 — teacher-facing longitudinal report**, extending `api/portfolio_service.py`.
- **Release gate, before any of this reaches a live student:** the Appendix E rewrite. E
  describes pseudonymization of names and ids; it does not describe **durable
  cross-assignment retention of student writing**, which is what this subsystem now does.
  Treat as a gate, not documentation cleanup.

## 10. Stop conditions

Return YELLOW rather than guessing if:

- extracting the shared scrub-and-segment helper would change the scored path's behaviour in
  any observable way;
- the new segmentation stage cannot claim mid-prompt fragments without breaking
  `test_segments_tile_the_whole_text` or the full-prompt-copy precedent;
- removing the `unknown` origin turns out to affect `codec` round-tripping.

Return RED if a Canvas call, an attachment download, or a scoring change appears necessary —
that contradicts §2 and the batch is mis-scoped.

## 11. References (section-routed; do not read wholesale)

- `AGENTS.md` — *Non-negotiable guardrails*, *Executor responsibilities*, *Lean engineering
  defaults*.
- `api/dailywriting/__init__.py` — the seven invariants. Short, read in full.
- `api/dailywriting/core/ingest.py` — `ingest()` :51, scoring call :105.
- `api/dailywriting/core/segmentation.py` — stage pipeline `segment_submission` :319,
  `_find_exact` :129, `_find_fuzzy` :145, `_claim_embedded_quote` :447, stage 5 :407.
- `api/dailywriting/config/thresholds.py` — `EMBEDDED_QUOTE_MIN_TOKENS` = 5,
  `FUZZY_MATCH_THRESHOLD` = 0.85, `QUOTED_SOURCE_THRESHOLD` = 0.90.
- `api/tests/dailywriting/test_dw_segmentation.py` — the tests that constrain a matching
  change: :18, :28 (full prompt copy), :59, :79 (quoted source), :84 (tiling).
- `docs/reference/project-state.md` — pre-launch, 0 users, 1 through ~Dec 2026, clean breaks
  over migrations.
- Previous brief, closed GREEN and retired. Recover with
  `git show b2b89a0:docs/handoffs/CanvasExpert-WritingRecord-AssistantRead-BRIEF.md`.
  Relevant sections: §8.1 (ECR decision + measurement), §8.1a (ingest unscored), §8.1b
  (paragraph-break span defect), §8a.1 (rubrics out, purpose in). Read only if a decision
  here is unclear — this brief is the authority.

## 12. Execution result

_To be completed by the executor: traffic light, commit hash, changed files, commands and
counts, deviations, unresolved decisions._
