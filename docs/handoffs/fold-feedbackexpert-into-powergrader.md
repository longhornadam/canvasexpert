# Handoff: fold FeedbackExpert into PowerGrader, then retire the name

Status: **Planning / not started.** Written 2026-07-21.
Scope: source-level routing and naming only. No workspace artifacts, Canvas data, or
credentials appear here.

## TL;DR

The *workflow* fold is already most of the way done. PowerGrader is the single
teacher-facing owner of grading and reviewed AI scoring; the old FeedbackExpert
run/manual/push HTTP routes are retired; the `feedback_*` modules survive only as shared
engines that PowerGrader imports. See
[feedback-powergrader-parity.md](../reference/feedback-powergrader-parity.md).

What is left is almost entirely **name elimination**, and it is easy to do badly. Before
touching anything, internalize the three-way split below. Roughly 549 occurrences of the
string "feedback" exist in the Python/HTML/JS tree; only about a dozen files carry the
*product name* "FeedbackExpert." The goal is to remove the product name, not the domain
word.

## Execution log

**Phase A + single-surface invariant: done 2026-07-21.**

- A1: UI was already clean; templates/static carry no brand, only the domain noun. The
  `/feedback-expert` redirect is kept as bookmark compatibility.
- A2: brand scrubbed from `AGENTS.md`, `docs/README.md`, `api/webui/README.md`, and
  `workbench-canonical-flow-map.md`; PowerGrader named as owner.
- A3: the module map was rewritten neutrally and renamed to
  `docs/reference/powergrader-scoring-map.md` (it is current, useful content, not dead, so
  it was kept rather than retired). `feedback-scoring-contract.md` is current and accurate,
  left as-is; its one brand mention is already correct past tense.
- A4: reworded the `powergrader/privacy.py` docstring; annotated the `size_report.py`
  legacy-folder skip. `workspace.py` `LEGACY_FEEDBACK_NAME` is the single permanent
  reference, left as the authorized quarantine.
- Invariant: added boundary comments at both PowerGrader write sites
  (`session_actions.py`, `autopush_executor.py`) and a guard test,
  `api/tests/test_grading_surface_invariant.py`, asserting only PowerGrader writes
  `comment[text_comment]`. Full feedback/powergrader/workspace suites pass (78).

Left intentionally as historical engineering records (not teacher-facing, past tense, not a
live surface): `feedback-powergrader-parity.md` and the completed "Luna 6" milestone in
`local-first-execution-roadmap.md`. These are the migration's audit trail. They are the only
remaining candidates for a future zero-brand pass, alongside optional Phase B.

## Audit: is PowerGrader already the sole surface? (2026-07-21)

Yes, functionally. The write-path audit confirms the fold is already complete where it
counts:

- **Scoring student work + drafting/pushing feedback: PowerGrader only.**
  `powergrader/session_actions.py` and `powergrader/autopush_executor.py` are the only
  writers of `submission[posted_grade]` + `comment[text_comment]` for scored work. The
  surviving `feedback_*` routes are library-only (`/personas`, `/patterns` CRUD) with no
  write path. There is no second feedback surface today, only the leftover name.
- **Other Canvas grade-writes are Gradebook jobs, not scoring.** `gradebook_curves.py`
  (curve existing grades), `operation_ledger/adapters/sweep.py` (late penalties), and
  `gradebook_extensions.py` / `gradebook_policy.py` (due-date extensions, late-policy
  config) all touch grades, but none scores student work or writes feedback.

### The boundary to hold

> **PowerGrader owns scoring student work and all AI feedback.** It is the only code that
> may write `posted_grade` + `text_comment` as the result of grading. **Gradebook owns
> post-hoc adjustment** (curve, late penalty, extension, policy) and may write grades or
> policy, but never AI-drafted feedback comments.

These are not competing grading surfaces; they are different jobs. Keeping the line sharp is
the point of "sole surface": no one adds score-entry to Gradebook, and no one adds curving
to PowerGrader. Tightening here is naming cleanup plus this invariant, not re-plumbing.

## The three meanings of "feedback" (read this first)

1. **"FeedbackExpert" — the retired product/brand.** This is the thing to eliminate.
   Literal `FeedbackExpert` appears in ~12 files (list below).
2. **`feedback_*` module names — shared engines.** `feedback_vault`, `feedback_safety`,
   `feedback_scrub`, `feedback_pipeline`, `feedback_artifacts`, `feedback_results`,
   `feedback_contract`, plus `webui/config/feedback.py` and the `routes/feedback*.py`
   library endpoints. These are alive and load-bearing; PowerGrader imports them
   (`powergrader/ai_workflow.py`, `context.py`, and others). The name conflates "the
   product" with "the engine." Renaming them is legitimate but high-churn and belongs in
   the last, optional phase.
3. **"feedback" the domain noun.** Student feedback text, `feedback_pattern`,
   `feedback_present`, `_hash_feedback`, comment-push logic. This is core PowerGrader
   vocabulary and must **not** be renamed or scrubbed. Deleting this would be a bug, not a
   cleanup.

A blind find-and-replace of "feedback" will break the product. Every task below names its
targets explicitly.

## The one reference that must survive forever

`api/webui/workspace.py` defines `LEGACY_FEEDBACK_NAME = "FeedbackExpert"` and resolves the
historical `FeedbackExpert/` workspace folder **only when it already exists**, never
creating it. The parity doc's locked migration path states that `FeedbackExpert/` workspace
data stays read-compatible forever and that no batch deletion or migration is authorized.

So "eliminate all references" has exactly one permanent exception: the quarantined legacy
folder constant and the code that reads (never writes) that folder. The end state is a
single, clearly labeled `LEGACY_FEEDBACK_NAME` and nothing else. Do not chase that last
string to zero; chasing it means either breaking teachers' existing on-disk data or
silently migrating it, and neither is authorized.

## Goal, in two horizons

- **Horizon A — finish the fold.** Make PowerGrader the sole entry point in every
  user-visible and doc-visible place. No dangling "FeedbackExpert" in UI, READMEs, or
  navigation. The `feedback_*` engines keep their names for now.
- **Horizon B — retire the engine names.** Optionally rename the `feedback_*` modules to
  neutral, engine-accurate names so the product brand disappears from the code too, leaving
  only the legacy folder constant.

Horizon A is worth doing soon and is low risk. Horizon B is a larger mechanical refactor
with modest payoff; do it only if the "no brand in code" goal is worth the import churn.

## Ordered tasks (each independently shippable)

### Phase A — finish the fold (low risk)

**A1. Confirm the redirect and remove dead UI paths.**
`routes/pages.py::feedback_expert_page` already 307-redirects `/feedback-expert` to
`/powergrader?advanced=import`. Verify nothing in `static/` or `templates/` still links to
`/feedback-expert` as a primary destination, and that no nav element presents FeedbackExpert
as a peer Expert. Keep the redirect itself as a cheap bookmark-compatibility link.
Acceptance: grep the static/template tree for `feedback-expert` and `FeedbackExpert`; only
the redirect and legacy-compat comments remain.

**A2. Scrub the product name from docs and READMEs.**
Files with the literal name today: `AGENTS.md`, `docs/README.md`, `api/webui/README.md`,
`docs/reference/local-first-execution-roadmap.md`,
`docs/reference/workbench-canonical-flow-map.md`. Rewrite these so grading and AI scoring
are described as PowerGrader capabilities. Where history matters, say "formerly
FeedbackExpert" once, in past tense, rather than describing it as a live surface.
Acceptance: no doc presents FeedbackExpert as a current feature.

**A3. Retire or fold the two standalone reference docs.** (done: renamed to
`powergrader-scoring-map.md`; contract kept as current)
`docs/reference/powergrader-scoring-map.md` (formerly `feedbackexpert-module-map.md`) and
`docs/contracts/feedback-scoring-contract.md` describe the old product and the parked
scoring contract. Decide per doc: fold the still-true parts into a PowerGrader reference,
or mark SUPERSEDED with a pointer to the parity doc. The scoring contract is parked/dormant
(kept, not extended) per project history; keep it if a future auto-push might reuse it, but
label it dormant.
Acceptance: neither doc reads as describing a live, separate product.

**A4. Fix stray code comments that name the product.**
`api/powergrader/privacy.py` ("no new FeedbackExpert tree is created") and the header of
`api/webui/workspace.py` reference the name in comments. Reword to describe the *legacy
folder* neutrally, keeping the behavior. `tools/size_report.py` references the folder name
for reporting; leave the string only if it is reporting on the legacy folder, and comment
why.
Acceptance: no code comment implies FeedbackExpert is a current subsystem; the only live
string is `LEGACY_FEEDBACK_NAME`.

### Phase B — retire the engine names (optional, higher churn)

Do this only if the "brand fully gone from code" goal justifies touching every importer.
Each rename is one task; ship and run the suite between renames. Suggested neutral names:

| Current | Proposed | Notes |
|---|---|---|
| `api/feedback_vault.py` | `api/vault.py` | crown-jewel decoder; touch imports in powergrader/context.py etc. |
| `api/feedback_safety.py` | `api/safety_gate.py` | the hard/soft PII gate |
| `api/feedback_scrub.py` | `api/pii_scrub.py` | roster-wide scrub |
| `api/feedback_pipeline.py` | `api/scoring_pipeline.py` | parse/validate/reidentify helpers |
| `api/feedback_artifacts.py` | `api/scoring_artifacts.py` | SAFE/PRIVATE bundle writing |
| `api/feedback_results.py` | `api/scoring_results.py` | result readers |
| `api/feedback_contract.py` | `api/scoring_contract.py` | dormant contract |
| `api/webui/config/feedback.py` | `api/webui/config/scoring.py` | personas + feedback patterns |
| `api/webui/routes/feedback*.py` | fold into `routes/powergrader*.py` or `routes/scoring_library.py` | library API only |

Rename tests alongside (`test_feedback_*` → matching names). Keep the module-level "feedback"
domain terms (`feedback_pattern`, `feedback_present`) intact; those are not brand references.

Acceptance for B: `grep -rniE "feedback" --include=*.py` returns only the domain noun and
`LEGACY_FEEDBACK_NAME`; no module, route, config, or symbol carries the product name.

## Non-negotiables

- **Do not weaken the privacy path.** The vault, the hard/soft safety gate, and
  scrub-and-verify behavior must be byte-for-byte equivalent after any rename. A rename that
  changes gate behavior is a regression, full stop.
- **Do not create or migrate `FeedbackExpert/` workspace data.** Read-only, on-existence,
  forever. No batch deletion.
- **Do not rename the domain noun.** `feedback` as student-feedback text stays.
- **Do not add a second scoring schema or provider abstraction.** PowerGrader is canonical;
  the parity doc forbids a parallel path.
- **Hold the single-surface invariant.** Only PowerGrader writes `posted_grade` +
  `text_comment` as a grading result. Gradebook curve/late/extension/policy writes are the
  one allowed exception and never carry AI feedback. Any new feedback-drafting or
  score-entry UI is a PowerGrader change, not a new surface.

## Reference inventory (pre-Phase-A snapshot, 2026-07-21)

Literal `FeedbackExpert` appeared in these files before Phase A (kept for the record; most
are now scrubbed, see the execution log): `AGENTS.md`, `docs/README.md`,
`api/webui/README.md`, `docs/contracts/feedback-scoring-contract.md`,
`docs/reference/feedbackexpert-module-map.md` (now `powergrader-scoring-map.md`),
`docs/reference/feedback-powergrader-parity.md`,
`docs/reference/local-first-execution-roadmap.md`,
`docs/reference/workbench-canonical-flow-map.md`, `api/powergrader/privacy.py`,
`api/webui/workspace.py`, `api/tests/test_workspace.py`, `tools/size_report.py`.

Shared engines (keep behavior; rename only in Phase B): `api/feedback_vault.py`,
`api/feedback_safety.py`, `api/feedback_scrub.py`, `api/feedback_pipeline.py`,
`api/feedback_artifacts.py`, `api/feedback_results.py`, `api/feedback_contract.py`,
`api/webui/config/feedback.py`, `api/webui/routes/feedback.py`,
`api/webui/routes/feedback_common.py`, `api/webui/routes/feedback_library.py`.

## Suggested definition of done

- Phase A complete: a teacher never sees the word "FeedbackExpert" in the app or the docs,
  and PowerGrader is described as the owner everywhere. Legacy bookmarks still redirect.
- Phase B complete (if pursued): the product name exists in the codebase only as
  `LEGACY_FEEDBACK_NAME`, with a comment explaining why it stays.
- Full test suite green after each shipped task; privacy tests unchanged in intent.
