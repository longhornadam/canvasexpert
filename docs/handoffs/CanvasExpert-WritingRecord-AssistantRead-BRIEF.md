# Brief — Assistant read path for the longitudinal writing record

> **CLOSED — GREEN, accepted 2026-07-28. Not current authority. Do not route an executor
> here.** Superseded by `CanvasExpert-WritingRecord-ECRSubstrate-BRIEF.md`, which is the
> single active brief.
>
> Retained on disk only because this batch is **not yet committed**, so Git history does not
> yet hold its record. Delete this file in the commit that lands the batch — per AGENTS.md
> *Handoff and document hygiene*, Git history is the durable record and
> `docs/handoffs/` holds one current brief.
>
> Sections still cited by the active brief, worth carrying forward before deletion: §8.1
> (ECR-is-just-longer-writing decision), §8.1a (ingest unscored, with the measurement),
> §8.1b (paragraph-break span defect — a real, unfixed bug), §8a.1 (rubrics out, purpose in).

**Written 2026-07-28.** One vertical batch. Follow-on batches are
listed in §9 and are **not** in scope here.

---

## 1. Objective

A connected assistant can read one student's writing across time — pseudonymously,
read-only, from the local store — so it can coach the writer rather than mark a single
assignment. The teacher reads the same arc with real names through existing surfaces.

Today the substrate exists and nothing can read it. `api/dailywriting/` (landed
2026-07-27 in `3131c60`, `e9fdf40`) holds a per-student longitudinal record at
`_System/WritingReps/`, and it has **zero** MCP or web UI exposure — verified by grep:
no reference to `dailywriting` anywhere under `api/mcp_server/` or `api/webui/`. Its only
surface is `api/dailywriting/cli/`. So the teacher's actual goal — an assistant that knows
a student as a writer — is unreachable, and an assistant asked about it today will answer
from the PowerGrader-shaped tools it can see and get it wrong.

## 2. Why this is a read path and nothing else

The store already made the hard calls, correctly, and this batch must not relitigate them:

- Records are keyed on `canvas_id` on disk; everything above `store/` speaks pseudonyms;
  `store/codec.py` is the single translation point. A store keyed on the pseudonym string
  would orphan every record the moment a teacher used `regenerate_pseudonym`.
- `_System/` is the PRIVATE tier. `store/SCHEMA.md` → *Location* states the record belongs
  neither in the repo, nor in `For AI/`, nor in any outbound payload. **The store is
  private; this batch adds a projection, not a relocation.**
- `canvas_id` is in `feedback_safety._FORBIDDEN_KEYS`, so handing a stored record wholesale
  to a payload builder is hard-blocked on the key name alone.
- INV-1: scoring is history-blind. History drives feedback and sequencing only.

The consequence for this batch: the assistant-facing payload is **built by a projection
function, never by serializing a record.** Same discipline as
`writing_timeline.safe_projection()` — a strict whitelist rebuild, so a field added to
`Submission` later cannot silently become outbound.

## 3. Locked decisions

1. **New MCP tool `get_writing_history(pseudonym, since="", until="", include_text=False,
   max_text_chars=…)`.** Pseudonym-first, because that is the read pattern; the existing
   tools are all course/assignment-first and none of them can answer "how is this writer
   developing."
2. **`include_text=False` by default.** Matches the server instruction already in place
   ("Prefer narrow calls: include_text=false or specific pseudonyms first"). A 20-rep arc
   of full text is a large payload billed to the teacher's own key.
3. **Reads only through `Repository` + `codec`.** No new file reader, no direct path
   construction, no second store root resolution. `Repository.default()` already resolves
   workspace + vault.
4. **Route the payload through `pseudonym.gate()`** like every other student-data tool, and
   refuse on vault conflict via the existing `_vault_conflict_check`. Fail closed.
5. **The tool computes no trend, streak, or aggregate judgment.** It returns dated records.
   The assistant may reason about them in conversation; CanvasExpert authoring a
   cross-assignment conclusion would put a judgment in the payload where no code guard can
   sanitize it — `sanitize_process_observation` only inspects a model's prose. Existing
   derived fields the store already owns (`RollingProfile`, directive uptake) may be
   returned as-is; this prohibition is on **new** computation in the tool.
6. **`get_product_guide` gains a topic covering the writing record.** Without it an
   assistant will again confidently report the feature does not exist — the exact failure
   `68bcfe6` was written to close, one commit before the store landed.
7. **Nothing in this batch writes.** No ingest, no Canvas call, no store mutation, no
   gradebook column.

## 4. Scope and insertion points

| Change | File | Note |
|---|---|---|
| Projection builder | new, `api/dailywriting/projection.py` (or `mcp_server/`, executor's call) | Whitelist rebuild from store records. The one place a record becomes outbound data. |
| Tool implementation | `api/mcp_server/tools.py` | Alongside `get_submissions` (~line 751); reuse `_tabulate`, `_truncate_text`, `_vault_conflict_check`, `_open_vault`. |
| Tool registration | `api/mcp_server/server.py` | Thin `@mcp.tool()` wrapper returning `_compact(tools.get_writing_history(...))`. Also update `_FERPA_NOTICE` (~22-40): the instructions currently describe only PowerGrader-shaped tools. |
| Schema bump | `api/mcp_server/contract.py` **(not `server.py` — brief corrected 2026-07-28)** | `TOOL_SCHEMA_VERSION` 9→10, append 10 to `_SUPPORTED_SCHEMA_VERSIONS`, add `tool_schema_v10.json` mirroring `v9`'s format, update the tool list/count in `api/mcp_server/__init__.py`, and bump `len(live["tools"]) == 12` → `13` in `api/tests/test_beta075_mcp.py:51`. |
| Product guide topic | `api/mcp_server/tools.py` `get_product_guide` (~line 537) + the served doc under `api/default_docs/AI Authoring/` | One canonical text, served verbatim, per *one source of truth per artifact*. |
| Store read support | `api/dailywriting/store/repo.py` | Only if an existing reader does not already cover the window query. Prefer composing `submissions_in_window`, `scores_for`, `observations_in_window`, `read_profile`, `directives_for`. |
| Tests | `api/tests/dailywriting/`, `api/tests/test_mcp_server_tools.py` | See §6. |

Out of scope in these files: any change to scoring, segmentation, directive evaluation, or
the criteria JSON.

## 5. Acceptance criteria

Each is independently checkable without reading the implementation.

1. `get_writing_history` returns, for a known pseudonym, one row per submission in
   ascending date order, with score/possible, tier, student word count, and observation
   count — and **no** `canvas_id`, real name, SIS id, or section, at any nesting depth.
2. `feedback_safety.scan_payload(result, vault)["green"] is True` for a fixture roster
   whose real names appear inside the stored writing. Mirrors the existing
   `test_no_pii_sweep_scan_payload_green_for_submissions` pattern.
3. An unknown pseudonym returns a structured refusal, not an exception and not an empty
   success. A pseudonym absent from the vault raises `IdentityError` inside the store; the
   tool converts it to `{"ok": False, "error": …}` naming the roster-sync remedy.
4. `include_text=False` (the default) emits no stored writing text anywhere in the payload;
   `include_text=True` emits text truncated to `max_text_chars`, and the truncation happens
   **before** the gate so the scan covers exactly the bytes that leave.
5. A vault conflict copy present on disk causes refusal, not a partial answer.
6. Adding a new field to `Submission` does not change the tool's output — asserted by a
   test that adds an unexpected key to a stored document and confirms the projection drops
   it.
7. `get_product_guide` returns the writing-record topic, and its text is the same bytes as
   the served contract file.
8. No new module under `api/dailywriting/` imports `api.canvas`, `requests`, or any Canvas
   transport.

## 6. Named verification gate

```bash
python -m pytest api/tests/dailywriting api/tests/test_mcp_server_tools.py -q
```

Plus the full `api/tests` suite for regression. Three tests fail environmentally and are
**not** caused by this work — confirm against `dev` before investigating either.

Proportional manual check: none required. This batch renders no UI. Do not start the app to
"verify" a read path that has no visual surface.

## 7. Explicit non-goals

- **No ECR / tracked-DOCX ingest.** See §8 — it needs a decision first.
- **No Writing Timeline integration.** There is currently zero coupling between
  `api/powergrader/writing_timeline.py` and `api/dailywriting/` (verified by grep), and
  this batch does not add one.
- **No pseudonym format change**, no scrub changes, no vault changes. Batch 2.
- **No teacher-facing report.** `api/portfolio_service.py` already builds a real-name
  chronological writing DOCX; extending it is a later batch, not this one.
- **No further naming work.** Already done ahead of this batch: `SYSTEM_NAME` is
  `WritingReps`, and `store.repo.STORE_FOLDER` now derives from it instead of repeating
  the literal, so the store folder is `_System/WritingReps/`.
- **No write path, no Canvas call, no scheduled job.**

## 7a. Decisions resolved before execution (2026-07-28)

Closed by the senior after repository recon, so the executor does not guess. §8.2 and
§8.3 below are settled by items 2 and 3 here.

1. **No new `Repository` reader.** Verified: `submissions_in_window` (351), `scores_for`
   (375), `observations_in_window` (392), `directives_for` (415), `read_profile` (336),
   `current_tier` (422), `read_rep` (246) already cover the window query. The projection
   composes them. §10's first stop condition does not fire; §4's "Store read support" row
   is empty.
2. **§8.2 resolved — `RollingProfile` IS assistant-visible.** INV-6 already says anything
   in a profile is renderable to the student, and a coach reading it is strictly weaker
   than the student reading it. Locked decision 5 permits returning store-owned derived
   fields as-is, and `per_criterion_rate` / `active_patterns` / `next_focus` /
   `best_piece` / `ready_for_tier_advance` are precisely the coaching signal. Projected
   through the same whitelist as everything else, not serialized.
3. **§8.3 resolved for this batch — there is no Section 3 to project.** Delivered feedback
   is not stored (§8a), and §7 forbids adding a write path. Batch 1 therefore emits no
   feedback section. Whether feedback becomes a stored record stays open for a later
   batch; it does not block this one.
4. **`include_text` governs STUDENT text only.** `raw_text`, observation `evidence_span`,
   observation `claim_text`, and any directive-evaluation `evidence_span` are quotes from
   student writing and are omitted entirely when `include_text=False`.
   `AssignmentContext.prompt_text` is teacher-authored — `put_rep`'s docstring states a rep
   "carries no student data" — and is **always** included, truncated to `max_text_chars`.
   It has to be: §8a.1 makes prompt-text purpose inference the Batch 1 fallback, which is
   impossible if the default call hides it.
5. **Reuse field names already in `feedback_safety._TEXT_FIELDS`.** The gate is
   field-name-keyed and scans nothing else. `raw_text`, `evidence_span`, `claim_text`,
   `next_focus`, `prompt_text`, `student_facing_text`, and `text` are already listed. A
   projection that invents `student_text` or `excerpt` would come back green unscanned —
   the exact failure `test_dw_outbound_gate.py` exists to catch. Prefer an existing name;
   if a genuinely new one is unavoidable, add it to `_TEXT_FIELDS` *and* to
   `DAILYWRITING_TEXT_FIELDS` in that test.
6. **The tool name clears the forbidden-substring check, barely.**
   `api/tests/test_beta075_mcp.py:52` rejects any tool name containing `write`, `update`,
   `comment`, `push`, `delete`, `create`, or `canvas`. `get_writing_history` is safe
   because "writing" does not contain "write". Do not rename it to anything with "writer"
   or "write" in it.
7. **This tool is a new shape: student data with no `course_id`.** It skips
   `_course_gate_check` (the store has no course concept) but still requires `_open_vault`
   and `pseudonym.gate`. It is not mirror-backed, so no staleness refusal applies. Say so
   in a comment — the module doctrine at `tools.py:1-20` currently pairs "no course_id"
   with "no safety gate", and this is the first tool to break that pairing.

## 8. Open decisions the senior must make (do not guess)

1. ~~**How an ECR enters the store.**~~ **RESOLVED 2026-07-28 by the teacher: an ECR is
   not a new record kind. It is just a longer piece of writing, ingested as an ordinary
   `Submission` through the existing pipeline.**

   All three options this section had been weighing are rejected: no second record kind,
   no `source` discriminator with optional fields, no dual-store read in the projection.
   The original framing — "an extended constructed response is a different animal,
   rubric-scored by PowerGrader" — imported PowerGrader's *grading* concern into a
   subsystem that answers a different question. §8a.1 already drew that boundary: the
   writing record answers "how is this writer developing," PowerGrader answers "why this
   score." Under that boundary the length of the piece is the only thing that actually
   changes, and length is not a modeling problem.

   Consequences, which shrink Batch 3 substantially:
   - Nothing in `core/models.py` changes. `Submission`'s invariants stay intact because
     nothing is being forced into them — a 900-word response has a `rep_id`, segments, a
     `student_word_count`, and a submitted timestamp exactly like a 90-word one.
   - No change to `store/`, `codec.py`, or `projection.py`. The projection already handles
     `score is None`, so an ECR ingested without a checklist score projects cleanly today.
   - Batch 3 reduces to wiring longer text into the existing ingest path. It is no longer
     an architecture batch.
   - `AssignmentContext.word_cap` is already `int | None`; a larger cap or no cap needs no
     code.

   **1a. Follow-on decision, locked 2026-07-28 after measurement: an ECR is ingested but
   NOT checklist-scored.** `Score` is simply absent for it; `projection.py` already emits
   `total`/`possible`/`status` as null when `score is None`, so this costs no code.

   The earlier draft of this section called the scoring heuristics "weaker on a
   five-paragraph essay." That was wrong in a way worth correcting, because it understated
   the failure. The tier 2-4 checklists say *"My thesis is one sentence, and my argument
   comes after it"* — thesis-first is a **taught constraint**, and `CheckInput.thesis`
   returning `sentences[0]` (`core/scoring.py:167`) faithfully measures what students were
   told to do. No checklist at any tier mentions a hook, because a 90-word rep has no room
   for one. Real extended writing does. So the failure is not gradual degradation, it is
   **inversion**: a student who opens with a proper hook has the hook scored as their
   thesis, and `arguable`, `specific`, and `answers_prompt` all read that same sentence.
   Better writing scores worse, on three criteria at once.

   Measured against invented 446 / 803 / 1356-word essays through the real ingest path:
   `thesis_arguable` failed with `needs_judgment=True` on **all three**, because the stance
   was stated in sentence 2. Separately, `commentary_connects`' thesis-overlap share rose
   33% → 67% → 80% across the three sizes on materially the same argument — longer text
   drifts checks toward automatic pass. Scoring a five-paragraph essay against a checklist
   written for one-sentence reps produces confidently wrong numbers, and wrong numbers in a
   coaching record are worse than no numbers.

   Rejected alternative: a tier-5 criteria set that *locates* the thesis rather than
   assuming its position. That is real scoring work, and it trades away the determinism the
   substrate is built on — the scorer deliberately returns `needs_judgment` rather than
   guess, and thesis-detection is guessing. Revisit only if unscored ECRs prove too thin in
   practice.

   **1b. Known defect found during the same measurement — recorded, not scheduled.**
   `CheckInput.commentary` rebuilds text with `" ".join(sentences)` while a submission
   stores `"\n\n"` between paragraphs, so once commentary spans a paragraph break the
   reconstruction is no longer a literal substring of `scored_text`. `_span_of`
   (`core/scoring.py:135`) requires an exact match, returns `None`, and `observations.py`
   then drops the observation because INV-3 requires evidence. The score still records
   *unmet*; nothing reaches the observation record, so it never enters the rolling profile
   or the student's feedback. **A silent drop.**

   Reproduced independently with a five-sentence text: identical content scores
   `span=present` as one paragraph and `span=None` as three. Requires two or more
   commentary sentences straddling a break — a single trailing sentence does not trigger it.

   Not scheduled as its own batch: daily reps are single-paragraph in practice, unscored
   ECRs never reach these checks, and the pilot has no users yet. Fix it in whatever batch
   next touches `core/scoring.py`. Do not let it be rediscovered from scratch.
   - A 20-piece arc containing several multi-page ECRs is a much larger payload at
     `include_text=True`. Locked decision 2 already defaults it off; `max_text_chars`
     bounds the rest.
2. **Whether `RollingProfile` is assistant-visible.** INV-6 says anything in a profile is
   renderable to the student, which argues yes. Not locked here because it changes the
   payload shape.
3. **Whether delivered feedback becomes a stored record** — see §8a. Affects whether this
   batch's payload has a Section 3 to project at all.

## 8a. The teacher's three-section model, checked against the store

Assessed 2026-07-28. Two of the three already exist; the third does not.

**Section 1 — Prompt & scaffolding: exists, keep as is.** `AssignmentContext`
(`core/models.py:186`) carries `prompt_text`, typed `scaffold_blocks`, `source_texts`,
`word_cap`, `tier`, and `criteria_set_id`, persisted in `reps.json` via `put_rep`/`read_rep`.
`store/SCHEMA.md` already gives the reason it must be durable: "a submission cannot be
re-scored without the prompt it was written against."

**Section 2 — Student submission: exists, and is stronger than the framing.** The concern
that a submission "might include scaffolding from the teacher" is exactly what
`core/segmentation.py` resolves. Every span is attributed to one of five origins
(`assignment`, `scaffold`, `student`, `quoted_source`, `unknown`) with a confidence and a
method, and `student_word_count` counts `student` spans only — a student who copies the
prompt and adds four words has written four words. Do not add a separate
"scaffolding included" flag; it would be a weaker restatement of `Segment.origin`.

**Section 3 — Feedback received: does not exist. This is the real gap.**

- AI feedback is *assembled but never persisted*. `core/feedback.py` builds the message in
  a fixed order from score + directives + criteria; `store/SCHEMA.md` → *Layout* has no
  feedback partition and `repo.py` has no `append_feedback`.
- Teacher feedback has no representation anywhere in the package.

Why reconstruction is not good enough, which is the argument for storing it:

1. A regenerated message is not the message the student read. `core/feedback.py` states the
   pedagogy — "the checklist they were taught is the checklist they are measured against, and
   a reworded criterion is a different criterion." Criteria JSON is editable, the length cap
   drops optional parts, and the exemplar pair is selected from the section. Change any of
   those mid-year and the reconstruction diverges from the delivered text in exactly the way
   that matters.
2. Coaching's first question is "what have I already told this writer, and did they act on
   it?" The store answers the structured half through directives and uptake evaluation. It
   cannot answer what prose the student actually read.
3. Teacher feedback is the highest-value signal for an assistant that should complement the
   teacher rather than contradict them, and it is entirely absent.

Three constraints if it is stored — each of these is a decision, not a detail:

- **Delivered, not generated.** The record is written when feedback reaches the student, not
  when a model produces it. PowerGrader AI feedback is a draft until the teacher reviews and
  posts. A store that captured drafts would let the assistant build on advice the teacher
  rejected.
- **The exemplar pair is third-party content.** `core/feedback.py` already checks that no
  message contains a roster name or another student's pseudonym, because part 4 quotes a
  strong response beside a near-miss. Persisting the assembled message therefore persists
  another student's writing inside this student's record. Store the pair **by
  `submission_id` reference, not embedded text**, or the per-student record silently becomes
  multi-student data — the same edge as the handoff's refusal to generate a share worklist
  for a folder holding more than one student's files.
- **Append-only, last-wins, derived id**, matching every other record kind, so a re-delivery
  leaves the earlier text auditable without steering anything today.

### 8a.1 Rubrics are out. Purpose is in.

**Rubrics are explicitly not part of this record.** Considered and rejected 2026-07-28 on
context economy and on boundary. A five-dimension rubric with four levels of descriptor
prose runs roughly 600–1,000 tokens per assignment; across a twenty-piece arc that is
12–20k tokens of evaluation language consumed before the assistant reads one word the
student wrote, billed to the teacher's own key. What a rubric adds beyond the score is
descriptor prose, which is teacher-facing *evaluative* language — the least useful thing for
a coach. Per-criterion outcomes already exist as `ItemResult` on `Score`.

The boundary that keeps both subsystems lean: **the writing record answers "how is this
writer developing." PowerGrader answers "why this score."** A rubric question is a grading
question and belongs to the surface that owns grading.

**What is actually missing is the piece's purpose — the "why they write it" — and nothing in
the package encodes it.** Verified by grep: no `purpose`, `genre`, `mode`, or `audience`
concept exists. `tier` is a difficulty level. `ScaffoldBlock.kind`
(`stem|frame|instruction|example`) describes the form of the help, not the aim of the
writing. `prompt_text` *implies* purpose but buries it in prose.

Two reasons a stored label beats inferring it from `prompt_text` on every read:

1. **Inference is repeated and inconsistent.** Twenty prompts re-read and re-classified per
   conversation, with no guarantee the same piece classifies the same way twice.
2. **It is the top failure mode for a growth read.** A narrative followed by an argument
   reads as regression when the reader cannot see that the task changed. A stored purpose
   makes it a task change instead of a decline. This is the single cheapest guard against the
   assistant telling a teacher a student got worse when they were simply asked to do
   something different.

Keep it small — a short closed set (narrative / argument / explanation / analysis /
reflection) plus an optional audience string. `word_cap` and `source_texts` already exist and
should not be duplicated.

**Sequencing:** the field does **not** land in this batch. Today every record is a tier-N
daily rep against one criteria set, so purpose variance is near zero and a field with no
immediate consumer contradicts *Lean engineering defaults*. It earns its keep the moment the
record spans genres — i.e. with ECR ingest — so it belongs to Batch 3 alongside §8.1. Until
then Batch 1 projects what exists and the assistant infers purpose from `prompt_text`.

## 9. Sequenced follow-on batches (not this batch)

- **Batch 2 — pseudonym format and scrub correctness.** One-token pseudonyms from a
  curated science-vocabulary pool with an enforced pool test; drop `pseudo_first`/
  `pseudo_last` and the first/last token-mapping branch at
  `api/feedback_scrub.py:106`; map a roster token owned by 2+ students to a neutral
  placeholder instead of one student's pseudonym (siblings/cousins currently
  cross-contaminate); add `dup_last` to `find_collisions`; remove the six pool tokens that
  collide with `COMMON_WORDS` (`lake, olive, river, stone, storm, sunny`); stop the roster
  collision guard depending on whether a caller passed `roster_names`.
  **Not time-pressured** — the store keys on `canvas_id`, so no on-disk key depends on the
  pseudonym string. Consumers: the vault, `feedback_scrub`, `api/dailywriting/core/scrub.py`,
  `api/webui/routes/names.py`, `roster.py`, `roster_updates.py`, `work_registry/providers/
  roster_warnings.py`, and the roster inline-edit JS.
- **Batch 3 — ECR ingest.** No longer gated: §8.1 is resolved, and an ECR is an ordinary
  `Submission`. Reduced to wiring longer text into the existing ingest path, with no model,
  store, codec, or projection change. Still carries the `AssignmentContext` purpose field
  (§8a.1) — the resolution of §8.1 does **not** dispose of that field. Purpose earns its
  keep because the record starts spanning genres, and a narrative following an argument
  still reads as regression to a reader who cannot see that the task changed. That is true
  whether or not the longer piece is a separate record kind.
  **Writing Timeline coupling is now a separate question**, deliberately not folded in
  here: it was only ever bundled with ECRs because ECRs were assumed to be
  PowerGrader-shaped. Scope it on its own merits.
- **Batch 4 — teacher-facing longitudinal report**, extending `portfolio_service.py`.
- **Release gate, before any of this reaches a live student:** the Appendix E rewrite.
  E is the project's honesty document. It describes pseudonymization of names and ids;
  it does not describe document metadata, and it does not describe **durable
  cross-assignment retention of student writing**. Shipping an assistant that reads a
  term of a child's writing while E is silent on it makes the most honest document in the
  project inaccurate. Treat as a gate, not documentation cleanup.

## 10. Stop conditions

Stop and return YELLOW rather than guessing if:

- an existing `Repository` reader does not cover the needed window query and adding one
  would change append/read semantics;
- the projection cannot produce a payload that passes `scan_payload` without weakening the
  scan;
- §8.1 or §8.2 turns out to block the product guide text;
- the tool would need `Submission` or any store model to change shape.

Return RED if a Canvas call, a store write, or a `For AI/` write appears necessary — that
contradicts §2 and the batch is mis-scoped.

## 11. References (section-routed; do not read wholesale)

- `AGENTS.md` — *Non-negotiable guardrails*, *Executor responsibilities*.
- `api/dailywriting/__init__.py` — the seven invariants. Load-bearing, short, read in full.
- `api/dailywriting/store/SCHEMA.md` — *Location*, *Identity*, *Invariants enforced at this
  boundary*.
- `api/dailywriting/store/identity.py` — the pseudonym↔canvas_id boundary.
- `api/mcp_server/tools.py` — `get_submissions` (~751) as the shape precedent,
  `get_product_guide` (~537), `_open_vault` / `_vault_conflict_check` (~260-286).
- `api/mcp_server/pseudonym.py` — `gate()` and the violation sanitizer.
- `docs/reference/project-state.md` — pre-launch, 0 users, clean breaks over migrations.
- `docs/handoffs/senior level/CanvasExpert-WritingTimeline-HANDOFF.md` — §1 *Invariants*,
  §8 *Honest limits*. Not implementation authority for this batch.

## 12. Execution result

**GREEN**, after one senior-directed correction round. No commit made (per instructions,
left in the worktree for senior review).

### Correction round — what changed and why

The first pass reported GREEN with a real defect and several tests that could not have
caught it. The senior's review (six items) found:

1. **Defect: `ItemResult.note` leaked student prose at the default `include_text=False`.**
   `core.scoring` interpolates a slice of the student's own thesis/argument/commentary into
   several notes, and the note was emitted unconditionally. Fixed by gating it behind
   `include_text` in `_item_result_row` (`api/dailywriting/projection.py`), same as
   `evidence_span`. `item_id`, `met`, `needs_judgment` stay unconditional.
   Attempting to add the field to `feedback_safety._TEXT_FIELDS` under its model name
   (`note`) broke two pre-existing tests in `test_feedback_safety.py` — a bare `note` key
   already carries different, non-text (structural exact-value id) semantics elsewhere in
   this codebase, so reclassifying it as free text silently weakened that other usage's
   hard-block coverage for ids under 5 characters. Renamed the outbound key to `score_note`
   instead (a genuinely new name, per the brief's §7a.5 fallback), added `score_note` to
   `_TEXT_FIELDS` and to `test_dw_outbound_gate.py`'s `DAILYWRITING_TEXT_FIELDS`, and reverted
   the `note` addition to both. `DirectiveEval.note` stays unconditional and untouched: it is
   built only from teacher-authored detector config (`core.directives.run_detector`), never
   from student prose.
2. **AC2 test was vacuous.** `green is True` cannot detect a name leak (a roster name in a
   `_TEXT_FIELDS` value is a SOFT finding, and `green = not hard`). Added `verdict["soft"] ==
   []` to the positive test and corrected its docstring (fixture 8's stored `raw_text` is
   already scrubbed by ingest; the real name is in the *input*, not what is served). Added
   `test_get_writing_history_scan_payload_can_actually_go_red`, a companion proving the sweep
   can fail on a structural identity key or a real id in free text.
3. **AC6 test exercised the codec, not the projection.** Kept it, relabeled honestly as codec
   robustness (`test_the_codec_ignores_an_unexpected_key_on_a_stored_document`), and removed
   the comment that overclaimed what it proved. Added the real test,
   `test_the_projection_drops_a_field_no_dataclass_ever_declared`: attaches an undeclared
   attribute to a live `Submission` via `object.__setattr__` and calls
   `projection.build_history_payload` directly, with no codec step in between to have already
   dropped it.
4. **AC1 sortedness was unfalsifiable, and directives/profile were never leak-swept.**
   `Repository.submissions_in_window` always returns pre-sorted results, so no test that goes
   through the repository can ever fail if `build_history_payload`'s own `sorted(...)` were
   deleted. Added `test_build_history_payload_sorts_regardless_of_input_order`, which calls
   the projection directly with submissions in reverse order and nothing upstream to have
   sorted them. Separately rebuilt the MCP-level AC1 test to add a directive and a profile to
   the fixture store (previously never populated, so `_directive_row`/`_profile_row`/
   `_pattern_row`/`_eval_row`/`_ref_row` were never exercised by the leak sweep at all) and to
   use two submissions in the same month partition for realism.
5. **AC4 never tested truncate-before-gate ordering**, only final length (identical under
   either ordering). Added a pair of tests that write a submission straight to disk (bypassing
   `core.ingest`'s scrub check, same technique as the AC6 test) with a hard-blocking real id
   either past or before `max_text_chars`: the far case must succeed (truncation removes the
   id before the gate ever sees it) and the near case must still refuse. Only together do the
   two prove the order.
6. **AC5 checked `ok is False` but not the exact key set.** Added `assert set(result) ==
   {"ok", "error"}`, matching the AC3 pattern.

### Self-check performed before reporting GREEN (as requested)

Built a store from every `singles.json` fixture through the real ingest pipeline, then called
`get_writing_history` for each fixture's own pseudonym with `include_text` and `max_text_chars`
left at their true defaults (only `since`/`until` were overridden, to `2026-01-01`..`2026-12-31`
— necessary because every fixture is dated fall 2026, after this sandbox's real clock of
2026-07-28, so the tool's own default two-year-lookback-from-today window would exclude every
fixture and make the check vacuous). For each fixture, checked whether the **trailing** 30
characters of that student's own raw text (a slice that can only be the student's own words,
never a copied prompt, since a copied prompt only ever appears as a *prefix*) appeared anywhere
in the dumped JSON of that student's own payload.

Result: zero leaks across all 9 fixtures. (An earlier version of this same check using each
fixture's *leading* 30 characters instead produced 9 false-positive "leaks" — every one was the
teacher-authored `prompt_text`, which is sanctioned to always appear, coincidentally sharing a
prefix with fixture 3's submission, which copies the prompt verbatim as part of the student's
own answer. The trailing-slice version does not have that confound.)

**Changed files** (cumulative, both rounds)

- `api/dailywriting/projection.py` (new) — the whitelist-rebuild projection, mirroring
  `writing_timeline.safe_projection()`'s discipline. `ItemResult.note` is gated behind
  `include_text` and emitted as `score_note`.
- `api/mcp_server/tools.py` — `get_writing_history` tool (alongside `get_submissions`),
  `_dailywriting_repository_factory` / `_pseudonym_gate` test seams, `get_product_guide`
  gains the `writing_record` topic, module docstring updated for the 13th tool and the
  "no course_id, no safety gate" pairing exception.
- `api/mcp_server/server.py` — `@mcp.tool() get_writing_history` wrapper, `_FERPA_NOTICE`
  mentions it, `get_product_guide` wrapper docstring mentions the new topic.
- `api/mcp_server/contract.py` — `TOOL_SCHEMA_VERSION` 9 -> 10, `_SUPPORTED_SCHEMA_VERSIONS`
  gains 10.
- `api/mcp_server/tool_schema_v10.json` (new) — mirrors v9 plus `get_writing_history`.
- `api/mcp_server/__init__.py` — docstring: 12 -> 13 tools, lists `get_writing_history`.
- `api/default_docs/AI Authoring/Writing Record (longitudinal writing history).txt` (new) —
  the `writing_record` product-guide topic, plain-prose house style matching
  `Writing Timeline (tracked assignments).txt` (the closest content sibling), ASCII-only.
- `api/feedback_safety.py` — `_TEXT_FIELDS` gains `score_note`, with a comment explaining why
  the model's own field name (`note`) was not reused.
- `api/tests/dailywriting/test_dw_outbound_gate.py` — `DAILYWRITING_TEXT_FIELDS` gains
  `score_note` (not `note`), with the same explanation.
- `api/tests/test_beta075_mcp.py` — schema version bumped to 10 in the assertion, `v9`
  contract block added, `len(live["tools"])` 12 -> 13.
- `api/tests/test_mcp_server_tools.py` — "get_writing_history" test section covering AC1-AC5
  plus the AC2/AC4/AC5 correction-round additions (soft-flag assertion, red-sweep companion,
  truncate-before-gate ordering pair, exact key-set check), `writing_record` product-guide
  tests (AC7), topic-list/error-message updates, tool count test renamed and updated to 13.
- `api/tests/dailywriting/test_dw_writing_history.py` (new) — AC6 (the real projection-level
  test plus the relabeled codec-robustness test), AC1's isolated sort test, and AC8 (no
  Canvas transport import).

Untouched, as instructed: `api/dailywriting/cli/_common.py`, `api/dailywriting/config/naming.py`,
`api/dailywriting/store/SCHEMA.md`, `api/dailywriting/store/repo.py` (no new reader needed;
§7a.1 confirmed the existing readers already cover the window query).

**Commands and counts**

```
python -m pytest api/tests/dailywriting api/tests/test_mcp_server_tools.py api/tests/test_beta075_mcp.py -q
188 passed
```

```
python -m pytest api/tests -q
1533 passed, 3 failed
```

All 3 failures are the project's documented `known-flaky-tests` baseline: the two
Windows-long-path failures (`test_feedback_pipeline.py::test_write_safe_and_private_auto_detects_compact_on_deep_path`,
`test_powergrader_packet.py::test_packet_workflow_budget_exception_stops_before_writes`, both
`WinError 3` on a deliberately 260+ char path, and known to fail identically on a stashed tree)
plus the load-sensitive `test_beta075_storage.py::test_spawned_vault_writers_preserve_both_students`
(which did not fail in the correction round's first full run, and did fail in the second —
exactly the intermittent-under-contention behavior the baseline record describes). None touch
`api/dailywriting`, `api/mcp_server`, `api/feedback_safety.py`, or any other file this batch
changed.

**Acceptance criteria, how each is checked (post-correction)**

1. `test_get_writing_history_returns_dated_rows_with_no_identity_leak` (rebuilt) — ascending
   dates, required per-row keys present, a populated directive and profile included in the
   leak sweep, no `canvas_id`/real name/SIS id/section anywhere in the dumped JSON.
   `test_build_history_payload_sorts_regardless_of_input_order` isolates the sort claim
   itself, independent of the repository's own pre-sorting.
2. `test_get_writing_history_scan_payload_green_with_include_text` (corrected) — asserts
   `soft == []` in addition to `hard == []`/`green`, with a corrected docstring.
   `test_get_writing_history_scan_payload_can_actually_go_red` proves the sweep is not a
   tautology.
3. `test_get_writing_history_unknown_pseudonym_is_a_structured_refusal` — unchanged; refusal
   naming the roster-sync remedy, `{"ok", "error"}` only.
4. `test_get_writing_history_include_text_default_false_omits_quoted_spans` (extended) — now
   also asserts `score_note` and `evidence_span` are absent from `per_item` when hidden and
   present when shown.
   `test_get_writing_history_truncates_before_the_gate_lets_a_far_id_through` /
   `..._still_blocks_a_near_id` pin the truncate-before-gate ordering itself.
5. `test_get_writing_history_refuses_on_vault_conflict` (extended) — now also asserts
   `set(result) == {"ok", "error"}`.
6. `test_the_projection_drops_a_field_no_dataclass_ever_declared` (new, the real AC6 test) —
   an undeclared attribute on a live `Submission`, added via `object.__setattr__`, is absent
   from `build_history_payload`'s output.
   `test_the_codec_ignores_an_unexpected_key_on_a_stored_document` (relabeled, kept) —
   codec-level robustness, honestly described as such rather than as proof of the
   projection's own whitelist.
7. `test_get_product_guide_writing_record_matches_served_file_bytes` (exact byte match) plus
   `test_get_product_guide_writing_record_states_the_tool_and_the_gap`. Unchanged.
8. `test_projection_module_imports_no_canvas_transport` — unchanged; source-text check on the
   one new module under `api/dailywriting/`.

**Deviations from the brief, with reason**

- The brief's guide-file style note ("H1 title, bold version/audience line, numbered
  `## N. SECTION` headers") describes the RubricForge/QuizForge authoring-skill files, not
  `Writing Timeline (tracked assignments).txt` — the file the brief itself names as the
  closest sibling. That file is plain prose with no markdown. Followed the named sibling's
  actual style (plain prose, ASCII, ELA-teacher voice) rather than the structural
  description, since the brief's own words ("since it is the other 'how this subsystem
  actually works' guide rather than an authoring skill") point the same way. Content, not
  format, was the point.
- `PatternSummary.evidence` (quoted spans inside `RollingProfile.active_patterns`) is gated
  behind `include_text`, even though §7a.4's enumerated text-field list does not name it
  explicitly and §7a.2 says profile fields may be returned "as-is." Resolved this in favor
  of AC4's blanket, testable wording ("no stored writing text anywhere in the payload...at
  any nesting depth") over the narrower reading of §7a.2, since §7a.2 itself says the profile
  is "projected through the same whitelist as everything else" — and everything else quoted
  from student writing is include_text-gated. Documented in `projection.py`'s module
  docstring and in `_pattern_row`'s comment.
- `ItemResult.note` is emitted outbound as `score_note`, not the model's own field name
  `note` — a correction-round finding (see above): a bare `note` key already carries
  different, non-text semantics elsewhere in the codebase, and reusing it would have quietly
  widened that other usage into free-text scanning.
- Added two small test seams to `tools.py` (`_dailywriting_repository_factory`,
  `_pseudonym_gate`) beyond what §4's file table names, for the same reason `_vault_factory`
  and `_enqueue_sync` already exist: without them the tool cannot be exercised offline
  against a fixture store, and `_pseudonym_gate` avoids a real shadowing bug (the tool's own
  `pseudonym` parameter, locked by §3.1's signature, would otherwise hide the `pseudonym`
  module inside that one function).
- Directive uptake (`directives_for`) and per-criterion checklist outcomes (`Score.per_item`)
  are included in the payload beyond the four fields AC1 names as mandatory, because locked
  decision 5 and §8a.1 both treat them as in-scope coaching signal ("Per-criterion outcomes
  already exist as `ItemResult` on `Score`") and because §7a.4 explicitly anticipates
  "any directive-evaluation evidence_span," which only makes sense if directives are in the
  payload at all.

**Unresolved decisions**

None. Every stop condition in §10 was checked and did not fire: the existing readers covered
the window query without a new one; the projection passes `scan_payload` green (hard AND soft)
in both `include_text` modes; §8.1/§8.2 did not block the product-guide text (§8.2 was already
resolved by §7a.2, and §8.1/ECR is explicitly out of scope per §7); and no store model needed a
shape change. No Canvas call, store write, or `For AI/` write was needed.
