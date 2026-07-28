# Writing Record Route Card

Routing scope: open this card only when the active handoff touches the longitudinal writing
record (`api/dailywriting/`), then read the relevant section. It is not global executor
context and does not replace a handoff's exact file/symbol list.

This card is the **durable** home for the subsystem's state. Briefs are retired when their
batch lands; what a new senior needs after that lives here.

## What this subsystem is

A per-student longitudinal record of writing, kept privately on the teacher's machine, so a
connected assistant can coach a writer across time rather than mark one assignment. It is
not a grading surface.

The boundary that keeps it and PowerGrader both lean: **the writing record answers "how is
this writer developing." PowerGrader answers "why this score."** A rubric question is a
grading question and belongs to the surface that owns grading. This has nothing to do with
Writing Timeline, which reads one submitted DOCX's own revision history.

## Entry points

- Substrate (models, scoring, segmentation, scrub, observations, profile): `api/dailywriting/core/`
- Private store: `api/dailywriting/store/` — see `store/SCHEMA.md`
- Outbound projection: `api/dailywriting/projection.py`
- Canvas mapping and ingest driver: `api/dailywriting/canvas_source.py`, `canvas_ingest.py`
- Uploaded-file acquisition (the only live Canvas path): `api/dailywriting/canvas_attachments.py`
- CLI: `api/dailywriting/cli/`
- Web trigger: `api/webui/routes/dailywriting.py`
- Assistant read: `get_writing_history` in `api/mcp_server/tools.py`
- Served guide: `api/default_docs/AI Authoring/Writing Record (longitudinal writing history).txt`

The seven load-bearing invariants are in `api/dailywriting/__init__.py`. Short, read in full.

## Ownership routes

| Concern | Owners |
|---|---|
| Record shape and invariants | `core/models.py` |
| Origin attribution of every span | `core/segmentation.py` |
| History-blind checklist scoring | `core/scoring.py` |
| Name removal before storage (INV-7) | `core/scrub.py` |
| Storage, keyed by `canvas_id` | `store/repo.py`, `store/codec.py` |
| Pseudonym ↔ canvas id | `store/identity.py`, backed by the shared vault |
| Anything that becomes outbound | `projection.py` — the single place |
| Canvas assignment → `AssignmentContext` | `canvas_source.py` |

## Where the record lives

`<workspace>/_System/WritingReps/`, the PRIVATE machine-state tier, beside the identity
vault and PowerGrader's sessions. The folder name derives from `config.naming.SYSTEM_NAME`
rather than being written twice. Nothing here belongs in the repo, in `For AI/`, or in an
outbound payload.

Records are keyed by `canvas_id` on disk; everything above `store/` speaks pseudonyms.
`canvas_id` is in `feedback_safety._FORBIDDEN_KEYS`, so a stored record handed to a payload
builder wholesale is hard-blocked on the key name alone.

## Two rules that are easy to break

**The outbound gate is field-name-keyed.** `feedback_safety.scan_payload` scans free text
only under names in `_TEXT_FIELDS`. A payload carrying student writing under an unlisted
name is not scanned at all and comes back green whatever is inside it. Any new outbound text
field must reuse a listed name or be added to the list *and* to `DAILYWRITING_TEXT_FIELDS`
in `api/tests/dailywriting/test_dw_outbound_gate.py`.

Corollary, learned the hard way: adding a key to `_TEXT_FIELDS` can *weaken* protection.
A value in a non-text field that exactly equals a real id is a hard block at any length;
inside a text field only ids at or above the length threshold hard-block. That is why
`ItemResult.note` is emitted as `score_note` rather than `note` — a bare `note` key already
carries structural-id semantics elsewhere.

**Scrub happens at ingest, before any span is stored.** A scrub applied later has already
been outrun by the spans quoted out of the text. This is the whole of INV-7's defence and it
constrains every future acquisition route.

## The one live Canvas path (`8960bda`)

Typed submissions are served entirely from the mirror and make zero HTTP calls — asserted, not
assumed. An uploaded file cannot be: the mirror keeps `attachment_names` but never bytes, and
Canvas leaves `body` empty for an `online_upload`. So `canvas_attachments` makes one focused
submission fetch plus one bounded download, and only for a mirror row that is an upload with no
body.

Three things about it are load-bearing:

- **It must never become an MCP tool.** `docs/mirror.md` design law 6 scopes the mirror-only law
  to the AI-facing tools; putting a live path under the assistant is what it forbids. An AST
  guard in `test_dw_canvas_ingest.py` holds the line, and the CLI and web route are the only
  triggers.
- **`canvas_client` is the only Canvas caller.** Not `api/submission_transport.py`, which has
  neither 429 retry nor the coordinator's yield and cancellation — fine for one teacher-watched
  report, not for thirty unattended sequential fetches. `canvas_stream_get` is the streamed seam;
  `_physical_get`'s `stream` keyword is passed to `requests.get` only when set, so non-streaming
  callers see the arguments they always did.
- **`_docx_segments`' annotations are not student text.** `[Inline image N]`, `[Table]`,
  `[Heading N] ` are the extractor talking to a reader. `canvas_attachments.submission_text`
  strips exactly those and rewrites nothing else, or they would inflate `student_word_count`,
  be attributed to the student by segmentation, and be quoted back as evidence. A plain essay
  carries none of them — measured, and pinned by a test.

Only `.docx`, 10 MB cap enforced on the declared size and again while streaming, nothing written
to disk, and a re-run re-downloads because Canvas's signed URLs expire.

## Delivered batches

Read the commit, not a summary, when the detail matters.

| Batch | Commit | What landed |
|---|---|---|
| Naming | `e772f3f` | `SYSTEM_NAME` = WritingReps; store folder derives from it |
| Assistant read path | `b2b89a0` | `get_writing_history`, `projection.py`, MCP schema v10 |
| Extended-writing substrate | `ef40e01` | `ingest_unscored`, mid-prompt fragment detection, dead `Origin` value removed |
| Canvas typed ingest | `401c7c0` | `canvas_source.py`, `canvas_ingest.py`, CLI + web trigger |
| DOCX ingest | `8960bda` | `canvas_attachments.py`, the subsystem's first live Canvas calls, `canvas_stream_get` |

Retired briefs are recoverable: `git show <commit>:docs/handoffs/<name>`.

## Open decisions

**Which assignments feed the record.** Unresolved. The teacher's first answer — reuse the
Writing Timeline tracked choice — rests on a false premise: `is_tracked_assignment`
(`api/powergrader/writing_timeline.py:56`) is not a stored flag but a classifier for
`submission_types == {"online_upload"} and allowed_extensions == {"docx"}`. A typed
text-entry submission can never satisfy it. Three options, recommendation first:

1. **The ingest action is the opt-in** — no persistent flag; pointing at an assignment is
   the decision. Current implementation assumes this, and it requires no mechanism, so 2 and
   3 stay reachable without rework.
2. A Canvas assignment group, read via `assignment_group_id` (already in the catalog).
3. A CanvasExpert-owned per-assignment flag — the new store, UI, and staleness handling the
   others avoid.

**Whether delivered feedback becomes a stored record.** AI feedback is assembled but never
persisted, and teacher feedback has no representation at all. A regenerated message is not
the message the student read, and coaching's first question is "what have I already told
this writer." If stored: written on delivery not generation; exemplar pairs held by
`submission_id` reference, never embedded text, or the per-student record silently becomes
multi-student data.

**`AssignmentContext` purpose field.** A short closed set (narrative / argument /
explanation / analysis / reflection) plus optional audience. Not yet earned: it becomes
load-bearing once the record spans genres, because a narrative following an argument reads
as regression to a reader who cannot see the task changed. Until then the assistant infers
purpose from `prompt_text`.

## Known defects and dead ends

**Unfixed: paragraph-break span loss in `core/scoring.py`.** `CheckInput.commentary` rejoins
sentences with `" ".join(...)` while a submission stores `"\n\n"` between paragraphs, so once
commentary spans a paragraph break the reconstruction is no longer a substring of
`scored_text`. `_span_of` (`core/scoring.py:135`) returns `None`, and `observations.py` drops
the observation because INV-3 requires evidence. The score still records *unmet* and nothing
reaches the record — a silent drop. Needs two commentary sentences straddling a break.
Latent today: daily reps are single-paragraph and unscored ECRs never reach these checks.
**Fix it in whatever batch next touches `core/scoring.py`.**

**Scoring inverts on extended writing, which is why ECRs ingest unscored.** Tier 2-4
checklists say "my thesis is one sentence, and my argument comes after it", so
`CheckInput.thesis` returning `sentences[0]` is faithful to what students were taught. No
checklist mentions a hook, because a 90-word rep has no room for one. Real extended writing
does — and then the hook is scored as the thesis and `arguable`, `specific`, and
`answers_prompt` fail together. Measured on 446/803/1356-word essays: `thesis_arguable`
failed on all three with the stance in sentence two; `commentary_connects` drifted
33% → 67% → 80% on the same argument as length grew.

**Known, deliberate, and surprising: the general scrub pass over-redacts.** Any capitalised token
with no lexicon entry is treated as a name, sentence-initial included, so an essay opening "Dogs
make better pets" is stored as "[name] make better pets". Privacy-first by design
(`core/scrub.py` `_general_pass`), identical for typed and uploaded text, and unchanged by any
batch so far — but it will read as a bug the first time a teacher sees a real record, and test
fixtures in this subsystem are written around it on purpose.

**Dead end, do not re-attempt: `SequenceMatcher` reuse in segmentation.** Segmentation
dominates ingest cost (~13 ms/word on a tier-3 rep with a source passage; 96/288/576 words
measured at 789/3100/7475 ms). Reusing one `SequenceMatcher` via `set_seq2` was implemented
and measured at 0.83x / 0.91x / 1.05x — no win, slower at small sizes, segments identical.
The cost is in `ratio()` computing matching blocks, not the constructor. Any future attempt
must be algorithmic and must show a measured improvement with identical output.

## Verification discipline

The named gate for this subsystem:

```bash
python -m pytest api/tests/dailywriting api/tests/test_mcp_server_tools.py -q
```

**A green suite is evidence about the tests, not about the behaviour.** Three batches in
this subsystem shipped with verification gaps that a green suite did not catch: a no-PII
test that passed because the name had already been scrubbed out of the fixture, a test that
exercised the codec instead of the layer under test, an ordering assertion fed pre-sorted
data, and a shared-code-path change that silently altered two fixtures.

So, when touching anything shared: **diff `student_word_count` and segment origins across
the whole `singles.json` fixture corpus, before and after.** A pinned-fixture test in
`test_dw_segmentation.py` now guards this permanently. Prove every negative test can go red
— `test_dw_canvas_ingest.py`'s scrub-bypass positive control is the pattern.

**Environmental test failures are machine-specific — re-baseline on a new machine.** On the
original development machine, two tests fail from the Windows 260-character path limit
(`test_feedback_pipeline.py::test_write_safe_and_private_auto_detects_compact_on_deep_path`
and `test_powergrader_packet.py::test_packet_workflow_budget_exception_stops_before_writes`),
and `test_beta075_storage.py::test_spawned_vault_writers_preserve_both_students` is
load-sensitive under full-suite contention. Do not assume this list transfers. Establish the
baseline on a clean checkout first: `git stash`, run, record, restore.
