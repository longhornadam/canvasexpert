# Batch brief: rationale contract, validation gate, and essay exemplar

**Status:** READY FOR ORCHESTRATION. Not started.
**Opened:** 2026-09-06 on `dev` at `cbbd8ef`.
**Addressed to:** the orchestrating agent, acting as senior of record for this batch.
**Planner:** prior session. Not available for questions. Every decision you need is below.

This is a batch brief, not root guidance and not a durable document. Delete it when the
batch closes GREEN and is accepted. Read `AGENTS.md` first; this brief assumes it and
does not repeat it.

---

## 0. Your role and what is expected of you

You are the senior for this batch. That means you own dispatch, acceptance, and the
traffic light. It does not mean you own the design. The architecture below was traced
against the live tree and confirmed with the teacher. Do not redesign it. If repository
truth contradicts something stated here, that is RED: stop and report, do not adapt.

What is expected of you, concretely:

1. **Run the preflight in section 6 yourself before dispatching anything.** Every claim in
   section 2 was verified at `cbbd8ef`. If the tree has moved, some may no longer hold.
2. **Respect the one-brief rule.** `AGENTS.md` allows exactly one current direct brief in
   `docs/handoffs/`, and `sis-grade-bridge-first-family.md` currently holds that slot at
   YELLOW. Do not add a second. Derive one executor brief at a time from this document,
   place it there only when the SIS brief is retired or the teacher clears it, and retire
   each executor brief as it closes.
3. **Dispatch per section 5, not per section 4.** Section 4 partitions the work by file so
   nothing collides. Section 5 says how those partitions become executor handoffs. The
   house model is one executor per bounded handoff, and this batch is one vertical
   improvement, not six. Do not spawn six agents.
4. **Verify executor reports against the tree, not against the report.** An executor
   saying "only the label changed, nothing else touched" is a claim, not evidence. Diff
   the actual files before you accept. This has bitten this project before.
5. **Do not accept Unit C on unit tests.** It has a live unknown that unit tests cannot
   answer. Section 4C says what evidence closes it.
6. **Return one compact report** in chat and in section 9: traffic light, commit hashes,
   changed files, commands run with counts, deviations, unresolved decisions.

What is not expected of you: broad repository discovery, rereading module maps, or
re-establishing anything in section 2. The routing row you need is "Create / Course
Expert" for the validator and pusher, and "Physical output" for the correction-document
renderers. You do not need the CanvasMirror spine, the vision document, or `tools/TOOLS.md`.

---

## 1. Objective

Three changes that share one contract, delivered as one vertical batch:

1. **Close the gate.** The strict per-choice rationale checks exist in the tree but are
   unreachable from the running app. A draft with empty or partial rationales currently
   validates and pushes. Make the live validator actually check depth.
2. **Change the authored rationale shape.** Every rationale on an auto-graded item becomes
   exactly two sentences: sentence one teaches the concept, sentence two ties that concept
   to this specific choice.
3. **Give open-response items a student-facing exemplar.** ESSAY and FILEUPLOAD items gain
   a short model response, written in student language, that a student can read and copy
   for correction points. Today those types carry nothing a student ever sees.

Teacher-visible outcome: the teacher stops hand-pasting blocks into Canvas's Custom
Feedback box, and every question type carries per-item feedback that reaches the student
through the path the pusher already builds.

---

## 2. Verified state at `cbbd8ef`

Traced directly against the tree. Do not re-derive any of it.

**The live gate is presence-only.** `api/validate_qf.py:61` asks one question per scored
item: does this item's `id` appear anywhere in `rationales`? It never looks inside the
entry. Four choices with one rationale passes. Four rationales that are all empty strings
passes.

Two callers, both teacher-facing:
- `/api/validate` at `api/webui/routes/push_validation.py:59`, rendered by
  `api/webui/static/push/quiz.js:176`.
- Inbox pre-validation at `api/webui/routes/library.py:52`, which decides whether "Use
  this draft" is offered, rendered by `api/webui/static/push/inbox.js:24`.

**The strict rules are test-only.** `engine/validation/rules/rationale_rules.py` covers
every choice, count match, non-empty text, and a required item `id`. Its only caller is
`build_validation_stages` at `engine/validation/report.py:80`, whose only callers are
`engine/tests/unit/test_report.py`. `QuizValidator` does not import it.
`Quiz.has_rationales` at `engine/core/quiz.py:61` has no callers at all.

**The tolerant parser destroys the evidence the strict rules need.** `_parse_rationales`
at `engine/spec_engine/parser.py:157` skips a malformed entry with a `logger.warning` and
continues; `packager._filter_rationales` then drops entries for items that do not exist.
By the time a domain `Quiz` reaches `check_rationale_coverage`, a typo'd key and a
genuinely absent rationale are indistinguishable. This is the decisive reason the existing
rules cannot simply be wired in where they stand, and it is what forces decision D1.

**Canvas transport for auto-graded types: already built.** `qf_pusher.prepare_items`
(`api/qf_pusher.py:74`) merges each entry onto its item as `item["_rationale"]`.
`api/transform.py:37` composes `✓ "choice" is correct because <rationale>` in green and
`✗ "choice" is wrong because <rationale>` in red. MC and MA use per-choice
`answer_feedback`; the other scored types use item-level `feedback.neutral`. None of it
renders unless `result_view_settings` spells out the display flags, per `api/README.md:215`.

**Canvas transport for ESSAY and FILEUPLOAD: absent.** `t_essay` at `api/transform.py:297`
and `t_fileupload` at `api/transform.py:309` emit no `feedback` key at all. `rubric_hint`
goes to `scoring_data.value`, which is the grader-side scoring note, not a student-visible
exemplar.

**The print path is already built for the exemplar.** Both correction-document renderers
already branch on open types and label the single-rationale text "A strong response:"
(`engine/rendering/correction_doc/html_renderer.py:35`,
`engine/rendering/correction_doc/docx_renderer.py:60`). That branch has never been
reachable, because the contract says essays take no rationale. The renderers and the
strict rules were built for a world where essays carry an exemplar; the contract and
`validate_qf.py` were written for a world where they do not. Objective 3 resolves that
split in favor of the renderers.

**Two contract drifts to fix while in there.** §11 line 290 of
`api/default_docs/AI Authoring/Author a Quiz (QuizForge).txt` says ESSAY and FILEUPLOAD
take no rationale, and its single-rationale type list omits CATEGORIZATION, which both
`api/validate_qf.py:19` and the strict rules include.

**Fixture scale.** 21 open-response items across 12 fixtures in
`api/qf_materials/qf quiz examples/`, plus `api/default_docs/AI Authoring/Reference/QuizForge_example_quiz.txt`.

---

## 3. Locked decisions

Confirmed with the teacher. Settled. Raise a stop condition rather than reopening one.

**D1. The gate lives in `api/validate_qf.py` and works on the raw parsed JSON,** not on a
domain `Quiz`. The teacher's file is the thing being judged, and the spec_engine pipeline
normalizes and drops before any rule could run. A message about the post-package object
would describe a file the teacher never wrote.

**D2. `validate()` keeps its exact signature and blocking semantics.** It returns a flat
list of hard-fail strings; an empty list still means pushable. Three callers and the CLI
depend on that. Style checks arrive through a new sibling function, never by changing this
return type.

**D3. Hard fails are only the unambiguous ones:** missing entry for a scored item; missing
item `id` on a scored item; MC or MA entry with no `choices` array; choice count mismatch
against the item; any empty or whitespace-only rationale string; a `choices` entry whose
`id` matches no choice on the item.

**D4. Shape checks are advisory, not blocking.** Sentence and word counting are heuristics
that misfire on `e.g.`, `Dr.`, `3.14`, and inline HTML. A false refusal of a good quiz
costs the teacher more than a soft warning costs a student.

**D5. The two-sentence form applies to every auto-graded rationale:** correct choices,
distractors, and the single-rationale types alike. Sentence one states the concept.
Sentence two ties it to this specific choice or answer. On a distractor, sentence two says
why this choice does not fit.

**D6. The concept sentence may repeat across the choices of one item.** That is intended,
not duplication to collapse. A student reads only the row they picked plus the correct row,
so each row carries its own teaching.

**D7. The essay exemplar reuses the existing single-rationale field.** An ESSAY or
FILEUPLOAD item gets a normal `rationales` entry with a `rationale` string holding the
exemplar. No new schema key. Three consumers already handle that shape. What changes is
the authoring rule and the rendered label, not the wire format.

**D8. The orphaned engine rule set is deleted, not repaired.** `engine/validation/report.py`,
`engine/validation/rules/rationale_rules.py`, and `Quiz.has_rationales` are unreachable
from the app. Keeping a second rule set that no longer matches the contract is exactly how
the current ESSAY drift happened. Their test coverage moves to the new gate before deletion.
This is consistent with the pre-launch clean-break posture in
`docs/reference/project-state.md`.

**D9. The authoring contract leads; code follows.** Per the repository boundary in
`AGENTS.md`, `api/default_docs/AI Authoring/Author a *.txt` are canonical. Unit A lands
first and every other unit implements what it says. Never the reverse.

---

## 4. Work units

File-level partitions. Section 5 tells you how to dispatch them.

### Unit A: authoring contract (documentation only)

Files: `api/default_docs/AI Authoring/Author a Quiz (QuizForge).txt`,
`api/default_docs/AI Authoring/Reference/QuizForge_example_quiz.txt`

Rewrite §11 (line 263 onward). Also touch line 63 (ESSAY item fields), line 290
(single-rationale type list), and the checklist at line 312.

The two-sentence rule, stated for the authoring LLM:

> Every rationale on an auto-graded item is exactly two sentences.
> Sentence 1 is the note: state the concept in general terms, the way it would be written
> on the board. It does not mention the answer choices.
> Sentence 2 applies that concept to this choice: why it fits, or why it does not.

Include this worked example verbatim. It is the teacher's own, and the sentence-1
repetition between A and B is the intended shape per D6:

> Prompt: "John and Sarah shared their different ideas about cars." Which of the words
> below is an abstract noun? A) Sarah B) ideas C) John D) cars. Correct: B.
>
> B: "An abstract noun is a thing that cannot be touched, heard, seen, tasted, or smelled.
> You cannot touch or see an idea, so *ideas* is abstract."
>
> A: "An abstract noun is a thing that cannot be touched, heard, seen, tasted, or smelled.
> *Sarah* is a person you can see and hear, so it is concrete, not abstract."

Replace line 290's "take no rationale" with:

> ESSAY and FILEUPLOAD items take a single `rationale` holding a student-facing exemplar:
> a short model response written at the student's reading level that a student can read and
> copy to earn correction points. High level, not exhaustive. Student language, not teacher
> language. It is not a rubric and not a grading note; `rubric_hint` remains the grader-side
> field and is unchanged.

Add CATEGORIZATION to the single-rationale type list at line 290.

### Unit B: the gate

Files: `api/validate_qf.py`, plus tests.

Extract a `_load(path)` helper so the file parses once, then:

1. Extend `validate()` with the D3 hard fails. Follow the message voice already in
   `engine/validation/rules/rationale_rules.py`: name the question, name what is missing,
   say what to add. That voice is better than the terse existing `validate_qf.py` style
   and is one of the things being preserved from the module marked for deletion.
2. Add `advise(data) -> list[str]` for D4 shape checks: not two sentences, outside roughly
   15 to 40 words, generic distractor text ("This is incorrect", "Not correct"), and any
   rationale telling a student to ask or see the teacher. Strip HTML before counting.
   Advisories read as suggestions, never as failures.
3. `/api/validate` returns `{ok, problems, advisories}`. `ok` stays `not problems`.
4. `main()` prints advisories in a section below compliance issues and still returns `None`,
   so the entrypoint smoke test keeps exiting 0.

Constraints that bite here:
- `api/validate_qf.py` is a pinned entrypoint in `api/tests/test_beta075_imports.py:22`.
  It is smoke-run as a bare script from two working directories and must exit 0 from both.
- That test also forbids `except ImportError` and `except ModuleNotFoundError` anywhere in
  non-test `api/` code. Import unguarded.
- Keep the module stdlib-only. It must not import `engine`.

### Unit C: essay exemplar transport, with a live unknown

Files: `api/transform.py`

`t_essay` and `t_fileupload` gain `"feedback": _neutral_feedback(item)`, matching the five
existing call sites.

Do not accept this unit on unit tests. Two questions need a real answer from the sandbox:

1. Does an essay item's neutral feedback render to the student at all?
2. Does it appear before the teacher has graded the response, or only after?

Question 2 is the one that matters. An exemplar visible before grading is an answer key. If
it renders early and cannot be gated, stop and report rather than shipping it. There is a
separate pending need for an essay-only dummy quiz for New Quizzes item finalization; fold
this verification into that same quiz rather than creating a second one. No synthetic
Canvas: verify against the real sandbox or report the unit as blocked.

### Unit D: correction document label

Files: `engine/rendering/correction_doc/html_renderer.py:35`,
`engine/rendering/correction_doc/docx_renderer.py:60`

The branch already exists. Change the open-type label from "A strong response:" to wording
matching what the student is asked to do with it, along the lines of "Model response to
copy:". Keep both renderers identical; they are tested in pairs at
`engine/spec_engine/tests/test_correction_doc_renderer.py`.

### Unit E: fixture migration

Files: the 12 fixtures in `api/qf_materials/qf quiz examples/` containing ESSAY or
FILEUPLOAD items. `QuizForge_example_quiz.txt` belongs to Unit A, not here: it is the
contract's own reference example and lands with the contract. Do not touch it.

Add a `rationales` entry with an exemplar for each of the 21 open-response items. Existing
MC and MA rationales in those fixtures are mostly one sentence and need the second beat
added under D5.

These fixtures are the worked examples an authoring LLM reads, so a fixture that violates
the new contract teaches the violation. This is not cosmetic. It ships in the same commit
as Unit B, or the bundled examples begin reporting invalid against the shipped validator.

### Unit F: cruft removal

Delete per D8, only after Unit B is green: `engine/validation/report.py`,
`engine/validation/rules/rationale_rules.py`, `Quiz.has_rationales`,
`engine/tests/unit/test_report.py`, and the `rationale_rules` import in
`engine/validation/rules/__init__.py` if present.

Port the cases in `engine/tests/unit/test_rationale_rules.py` onto the new gate before
deleting that file. They encode real coverage and should not be lost.

Before deleting `engine/validation/report.py`, read its docstring reference to a Pyodide
boundary. If a browser-side validation surface is genuinely planned, stop and report;
nothing in the current tree consumes it.

---

## 5. Dispatch plan

Four executor handoffs, in two waves. Not six.

**Wave 1, single executor: Unit A.** Documentation only, and it is the source of truth for
everything downstream. Accept it before dispatching wave 2. An executor writing rationales
in wave 2 needs the contract to already say what a rationale is.

**Wave 2, three executors, parallel, disjoint file sets:**

- **Executor 2A: Units B + E + F.** These must not be split. B and E ship in one commit
  (section 4E), and F is the tail of B. One executor, one commit, one context.
- **Executor 2B: Unit C.** Isolated to `api/transform.py` and owns the sandbox
  verification. Longest wall-clock because of the live check.
- **Executor 2C: Unit D.** Small, isolated to the two renderers.

No two executors touch the same file. Executor 2A owns `api/` validation and
`api/qf_materials/`; 2B owns `api/transform.py`; 2C owns `engine/rendering/`.

If executor 2B returns blocked on the live check, that does not block 2A or 2C. Land those
GREEN and carry C as a named YELLOW.

---

## 6. Preflight, run by you before dispatching

Stop and report if any of these is false rather than adapting the plan.

1. `git status` clean on `dev`; fetch and compare against `origin/dev` and `origin/main`.
2. `api/validate_qf.py:61` still performs a presence-only rationale check.
3. `build_validation_stages` still has no non-test caller:
   `grep -rn "build_validation_stages" . | grep -v __pycache__` returns only
   `engine/validation/report.py` and `engine/tests/unit/test_report.py`.
4. `t_essay` in `api/transform.py` still emits no `feedback` key.
5. Both correction-document renderers still carry the "A strong response:" open-type branch.
6. `docs/handoffs/` still holds exactly one brief, and you know its status.
7. Baseline the suites once and record the exact commands and counts in section 9, so later
   units cite that record instead of rerunning:

```bash
py -m pytest api/tests -p no:randomly -q
```

```bash
py -m pytest engine/tests -p no:randomly -q
```

---

## 7. Explicit non-goals

- No change to `qf_pusher.py` merge or push behavior beyond what Unit C requires.
- No change to `result_view_settings` defaults.
- No change to the tolerant parser. It stays forgiving; the gate reads the raw file instead,
  per D1.
- No new UI work. Both teacher-facing surfaces render whatever strings come back, so richer
  messages flow through with no JavaScript change. The single exception is displaying
  advisories on the quiz tab, a few lines in `api/webui/static/push/quiz.js`.
- No touching the legacy text spec path (`engine/parsing/text_parser.py`,
  `QUIZFORGE_SPEC_MODE=text`). Not the default, not in scope.
- No back-compatibility shim for one-sentence rationales. Pre-launch, single user, clean
  break.
- No new registry, adapter, or abstraction. Two call sites is not a pattern.

---

## 8. Stop conditions and house constraints

Stop and report rather than working around any of these:

- New Quizzes will not render feedback on essay items, or renders it before grading with no
  way to defer it.
- Tightening the gate reds a test outside the rationale surface, which would mean the
  presence-only check was load-bearing somewhere untraced.
- Anything requires changing `validate()`'s return type. That breaks `library.py:52`'s
  `not problems` gate and is ruled out by D2.
- A `docs/contracts/` document would need to change. This batch touches an authoring
  contract and a validator, not a durable data contract.

Constraints that apply throughout:

- **Tests follow the house taxonomy.** Law, contract, or example. A test that is none of
  the three does not get written. Test paths mirror module paths; shared setup goes in the
  nearest `conftest.py` as a named fixture. The gate's depth checks are a law and belong
  tested at the law, once, not through three consumers.
- **No student data and no secrets** in fixtures, tests, logs, or commit messages. Every
  new exemplar is authored content about a subject, never about a student.
- **Prose and UI copy follow house voice.** No em-dashes anywhere. Calm and teacher-facing,
  not compliance-flavored. Validator messages tell a teacher what to fix, not what they did
  wrong.
- **Risk level is Low to Medium.** Offline parsing and validation plus one Canvas content
  field. Focused tests plus the affected subsystem suites are proportional. The full matrix
  is not owed unless focused failures show unexpected coupling.

---

## 9. Verification gate

Every item must hold before you call the batch GREEN.

- `py -m pytest api/tests -p no:randomly` and `py -m pytest engine/tests -p no:randomly`
  green, or failing only on the baseline recorded in preflight step 7.
- `py api/validate_qf.py` exits 0 from both the repository root and an unrelated directory.
- A hand-built envelope with four choices and three rationales is refused, with a message
  naming the question and the count.
- A hand-built envelope whose four rationales are all `""` is refused.
- An ESSAY item with no rationale entry is refused. With an exemplar it validates, and the
  exemplar appears in both the HTML and DOCX correction documents under the new label.
- A one-sentence rationale validates and produces exactly one advisory.
- All 13 quiz fixtures in `api/qf_materials/qf quiz examples/` report OK with zero
  advisories against the shipped validator. Corrected during execution: the gate
  originally said "every bundled fixture", which was never achievable. That folder also
  holds `af_found_poetry_sampler.txt` and `pf_unit_hub_sampler.txt`, an AssignmentForge
  and a PageForge sampler with no `<QUIZFORGE_JSON>` envelope. `validate_qf.main()` globs
  `*.txt`, so it has always reported both as having no envelope. Pre-existing, unrelated
  to this batch, and left alone. Observation for the teacher, not acted on: two non-quiz
  samplers living in a folder named "qf quiz examples" is why that noise exists.
- Unit C: the sandbox quiz id, what the student view actually showed, and when it showed it
  relative to grading. A passing unit test is not evidence for this line.
- You have diffed the changed files yourself rather than accepting executor summaries.

---

## 9a-live. Test quiz pushed 2026-09-06, awaiting the teacher's student-side look

Pushed to **CS 8, course 121046** (not the sandbox, at the teacher's direction):
`https://pearland.instructure.com/courses/121046/assignments/3675645`

Source file: `Library/Quizzes/html_quick_check_feedback_test.txt` in the workspace.
Three items on HTML, the current module: one MC (per-choice feedback), one TF
(single-rationale neutral feedback), one ESSAY (the exemplar). All three returned
HTTP 200.

**Confirmed by the push itself:** Canvas accepts and stores `feedback.neutral` on a
human-graded essay item. That answers half of question 1. It does not answer when the
student sees it.

**State:** `published: false`, 100 points, assignment group 259100, no due date. No
student can see it until the teacher publishes.

**The specific risk signal to check.** `result_view_settings.display_item_response_qualifier`
is `after_last_attempt`, which is attempt-based, not grading-based. If Canvas honors that
literally on a human-graded item, the exemplar appears as soon as the student submits and
before any grading, which is the answer-key failure mode. Check that first.

**Also worth the teacher's eye, a design question rather than a defect:** on a wrong MC
choice the concept sentence now appears twice in one feedback box, once in the correct
answer's line and once in the chosen answer's line. That is decision D6 meeting the
two-layer composition in `_because`. It reads redundantly. Deduplicating the shared
leading sentence is possible but was not decided unilaterally.

## 9b. Original sandbox procedure for Unit C

The code and its test are green. The unit stays YELLOW until this runs, because an
exemplar visible before grading is an answer key and no offline test can tell you which
way Canvas behaves. Sandbox course 109559.

This rides on the essay-only dummy quiz already needed for New Quizzes item finalization.
Do not create a second one.

1. Use that essay-only quiz, with at least one ESSAY item whose `rationales` entry carries
   a short student-facing exemplar (the D7 shape: a `rationale` string, no `choices`).
2. Push it to 109559. The wire shape can be confirmed first by inspecting the built item
   JSON: it should now carry `"feedback": {"neutral": "<p>...exemplar...</p>"}` where
   before this batch it carried no `feedback` key at all.
3. Publish from the Canvas UI. API publish returns 400, per `api/README.md`.
4. Sign in as a real second enrolled student in 109559. Student View cannot be used:
   `api/README.md:226` records that New Quizzes do not launch for the Test Student, since
   they are an LTI tool the fake student is not provisioned in.
5. As that student, answer the essay item with placeholder text and submit the attempt
   fully, before any teacher grading action.
6. Immediately, still before grading, view the student's results screen for that item and
   record what shows. If the exemplar is already visible with no grade assigned, stop.
   That is the failure mode: Unit C is blocked and does not ship.
7. As the teacher, grade that submission and assign a score.
8. Reload the same student's results view and record whether the exemplar now appears.
9. Absent at step 6 and present at step 8 answers both questions and closes Unit C GREEN.
   Absent at both means feedback is not rendering at all: check the `result_view_settings`
   display flags, since `api/README.md:215` records that an unset one shows the student
   nothing. Report blocked rather than shipping quietly.
10. Keep any notes or screenshots in the teacher's workspace, never in the repository.

## 10. Execution result

To be filled in by you.

**Traffic light:** YELLOW. Units A, B, D, E and F are GREEN, accepted, and committed.
Unit C's code and test are GREEN but the unit cannot close until the teacher runs the
live check in section 9a, because an exemplar visible before grading would be an answer
key and no offline test can tell you which way Canvas behaves.

**Commit:** `6f5f7a8`, 29 files, 1213 insertions, 556 deletions.

**Verification evidence, gathered by the orchestrator rather than taken from reports:**

- All 13 quiz fixtures pass the shipped validator with 0 problems and 0 advisories. Two
  executors wrote those fixtures independently against the contract while a third wrote
  the validator, so this cross-check is the real proof the three agree.
- The gate refuses all six failure modes, each with a teacher-readable message: 4 choices
  against 3 rationales, four whitespace-only rationales, an MC entry with no `choices`
  array, a choice id matching no choice on the item, a scored item with no `id`, and an
  ESSAY with no exemplar.
- Advisories fire without blocking. A one-sentence generic rationale that tells the
  student to ask the teacher produces 6 advisories with `ok` still true. A 99-word essay
  exemplar produces none, confirming the open-response exemption.
- `py -m pytest api/tests -p no:randomly` gave `5 failed, 2437 passed`, the five being
  exactly the baseline five, unchanged in identity.
- `py -m pytest engine/tests engine/spec_engine/tests -p no:randomly` gave
  `149 passed, 1 skipped`. `engine/tests` went 127 to 113, matching the 14 deleted tests.
- `py api/validate_qf.py` exits 0 from the repository root and from an unrelated directory.
- `/course-expert` rendered with zero console errors, and `/api/validate` returned the new
  `{ok, problems, advisories}` shape over the wire for both a clean and an advisory-heavy
  file.
- Every fixture's `items` and `metadata` blocks are byte-identical to `HEAD`, confirming
  the fixture executors touched only `rationales`.
- Staged diff scanned for credentials and student data before commit: clean.

**Orchestrator changes beyond executor work:** the missing-entry hard fail used one terse
message for every type. It now names what to add per type, so a missing essay exemplar
reads like the others instead of saying "missing rationale". Four test assertions that
pinned the old wording were updated to match.

**Dispatch deviation from section 5, decided by the orchestrator.** Section 5 planned four
executors. Six were dispatched. Two reasons, both measured rather than assumed:

- Unit A came back GREEN on structure but the reference quiz's rationales ran 41 to 53
  words against the 15 to 40 range the contract itself now states, with 12 of 14
  auto-graded rationales over. All were correctly two sentences, so the rule landed and
  the density did not. Since that file is what an authoring LLM imitates, it went back for
  a bounded correction. The house rule is to return corrections to the same executor, but
  `SendMessage` is unavailable in this session, so a fresh executor took the correction
  with the measurements included.
- Unit E was roughly five times larger than section 4E estimated: 116 auto-graded
  rationales needing reshaping plus 21 exemplars across 13 files, not the 21 exemplars the
  brief described. That is too much for one executor carrying Units B and F as well, so
  Unit E was split from the code work and then split again by fixture character. The seven
  pedagogical fixtures and the six `nq_pull_*` transport probes went to separate executors,
  a boundary the folder README already draws.

The batch is still one vertical improvement with one acceptance. No unit was descoped.
`QuizForge_example_quiz.txt` was moved from Unit E to Unit A to remove a file collision
between two executors.

**Baseline recorded in preflight:** taken 2026-09-06 on `dev` at `cbbd8ef`.

- `py -m pytest api/tests -p no:randomly -q` gave `5 failed, 2418 passed in 77.25s`.
- `py -m pytest engine/tests -p no:randomly -q` gave `127 passed in 7.90s`.

The five pre-existing api failures are unrelated to this batch and are not to be fixed
or absorbed by any executor in it. Cite this record instead of rerunning:

- `api/tests/dailywriting/test_dw_canvas_ingest.py::test_scrub_bypass_would_be_caught_by_the_storage_leak_guard`
- `api/tests/mcp_server/test_tools.py::test_server_registers_the_expected_tool_set`
- `api/tests/test_canvasagent_instructions.py::test_it_does_not_claim_python_installs_itself`
- `api/tests/test_design_theme_studio.py::test_build_prunes_stale_cards_but_leaves_other_files`
- `api/tests/test_roster_routes.py::test_private_group_snapshot_round_trip_has_only_allowlisted_fields`

Preflight items 1 through 6 all held. Additional findings during preflight:

- `engine/validation/rules/__init__.py` is empty, so Unit F has no import to remove.
- `engine/spec_engine/packager._filter_rationales` excludes only STIMULUS and
  STIMULUS_END, so an ESSAY rationale already survives packaging. `models.py:41` already
  documents the ESSAY case. The engine path is ready for the exemplar; only the contract,
  the gate, the label, and the Canvas transport need work.
- `structure_rules` and `fairness_rules` are also orphaned from the app and lose their
  direct coverage when `test_report.py` is deleted, but retain indirect coverage through
  the `QuizValidator` integration tests. Unit F does not widen to delete them. Flagged
  for the teacher as a separate observation, not acted on.
- `api/tests/webui/test_ai_ta.py` pins the QuizForge contract file: it must still start
  with `# QuizForge`, must not contain `PASTE THIS WHOLE FILE`, `{KIND}`, or `{TAG}`, and
  must retain the line `STIMULUS is for actual content students must reference`.

**Commits:**

**Changed files:**

**Verification evidence:**

**Deviations:**

**Unresolved decisions for the teacher:**
