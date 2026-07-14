# Execution brief: establish the canonical Workbench flow inventory

Status: **ready for implementation**

Risk: **low**

Executor: **external VS Code agent**

## Outcome

Canvas Expert has one short, durable map from each teacher-visible outcome to its
canonical current surface, route, browser owner, backend owner, and safety boundary.
The same map identifies candidate legacy surfaces that can be retired and proves why
they are candidates, without deleting or changing runtime behavior in this brief.

This is the prerequisite for trimming migration overlap deliberately rather than
deleting code because it is old or large. It should reduce future debugging context by
letting an agent begin at the current teacher flow instead of reconstructing the
Workbench migration from history.

## Locked decisions

- The product is a shared teacher Workbench, not a collection of independently
  featured mini-apps. A discrete capability is retained only when it has a distinct
  teacher outcome or a required safety boundary.
- For each outcome, document **one canonical teacher-facing flow**. The canonical flow
  may link into a Workbench tab, lens, or session; it need not imply that every route
  is physically merged.
- A route, template, script, helper, compatibility global, or test is a *retirement
  candidate* only with evidence that a canonical replacement exists and that current
  runtime callers do not require the old surface. "Legacy" in a name is not evidence.
- Keep the already-completed Course Expert surface retirement as accepted history:
  `/course-expert` is canonical for Quiz, Assignment, Page, Rubric, Download Work,
  Student Reports, and Quick Assignment. Do not reopen or re-audit its removed seven
  standalone pages or `push_service.py` as live candidates.
- Do not infer that all compatibility is redundant. Preserve candidates that protect a
  CLI workflow, a distinct supported API client, a safety/recovery boundary, a private
  data boundary, or an explicitly deferred browser migration.
- Test count is not a quality metric. The audit must identify tests by the distinct
  teacher behavior or safety regression they protect, including likely duplicates; it
  must not recommend deletion merely to lower a count.

## Scope

- Add `docs/reference/workbench-canonical-flow-map.md` as a concise current-state
  inventory. Cover these teacher outcomes:
  - Desk / choosing or continuing work
  - Course content creation and delivery
  - Gradebook actions
  - Roster and student-group actions
  - PowerGrader session setup, review, and push
  - FeedbackExpert scoring and feedback push
  - Settings / first-run configuration
  - Routines
- For every outcome, record in a compact table:
  1. canonical URL or entry point;
  2. canonical template and browser owner;
  3. backend/service or operation owner;
  4. relevant durable contract or module map;
  5. teacher-visible safety boundary; and
  6. any deliberately retained alternate path and its reason.
- Add a second table of retirement candidates. Each row must name the candidate,
  replacement flow, live callers/entry links found (or the search evidence that none
  exist), risk class, and a recommended next action: retain, retire in a named future
  batch, or needs product decision.
- Include a narrowly scoped test portfolio note for each candidate batch: retain
  focused safety/behavior checks, consolidate tests, or investigate duplicate coverage.
  Name test files only; do not redesign or edit them.
- Update `AGENTS.md` only if the resulting canonical flow map changes one of its
  current feature-map statements. Otherwise leave it unchanged.

## Out of scope

- Do not delete, move, rename, or alter runtime code, routes, templates, scripts,
  tests, contracts, configuration, or archived handoffs.
- Do not change navigation, Workbench composition, operation-ledger behavior,
  Canvas-write behavior, credential handling, FERPA boundaries, scheduled jobs, or
  external AI transmission.
- Do not run live Canvas or OpenRouter requests, start routines, open private
  workspaces, or inspect student-derived output.
- Do not turn every compatibility seam into a candidate. In particular, do not classify
  the legacy QuizForge streaming routes, CLI paths, Feedback SAFE/PRIVATE boundaries,
  or operation-ledger recovery seams as removable without direct consumer evidence.
- Do not create a broad test-cleanup plan or make test-count reduction an objective.

## Reference pattern and routing

- Existing completed retirement authority:
  `docs/handoffs/archive/course-expert-canonical-surface-retirement.md`
- Course content map: `docs/reference/course-expert-module-map.md`
- Gradebook map: `docs/reference/gradebook-module-map.md`
- Roster map: `docs/reference/roster-module-map.md`
- PowerGrader map: `docs/reference/powergrader-module-map.md`
- FeedbackExpert map: `docs/reference/feedbackexpert-module-map.md`
- Settings map: `docs/reference/settings-module-map.md`
- Operation write/recovery ownership: `docs/reference/operation-ledger-module-map.md`
- Released/deferred migration decisions:
  `docs/reference/operation-ledger-release-status.md`
- Current UI surface reference: `api/webui/README.md`
- Read project-local `TOOLS.md` before broad inspection. Use `rg` for callers,
  route registrations, templates, navigation links, script includes, and test targets.

Do not treat archived handoffs as current authority except where this brief explicitly
names an accepted decision or completed removal.

## Implementation requirements

1. **Start from teacher outcomes, not file trees.** Establish the entry point and
   teacher-visible result first. Trace only the current route/template/browser/backend
   chain needed to state canonical ownership.

2. **Separate supported alternates from migration overlap.** For every alternate route
   or compatibility seam encountered, classify it as one of: distinct supported
   workflow, required safety/recovery boundary, temporary migration compatibility,
   or unknown. Only the latter two can become retirement candidates, and unknown must
   remain a product decision rather than a deletion recommendation.

3. **Make evidence readable and cheap to maintain.** Prefer exact paths, symbols,
   routes, and short `rg` queries over copied source excerpts. The map should route a
   debugging session in under a minute; it is not an architecture history.

4. **Treat tests as evidence, not inventory bulk.** For each proposed retirement batch,
   state the minimal teacher behavior and failure/safety behavior that must remain
   covered. Flag exact duplicate/obsolete tests only when their asserted behavior is
   demonstrably covered by the canonical owner.

5. **End with at most three sequenced follow-up batches.** Each must be a coherent
   vertical retirement candidate—not a file-size cleanup—and must name its expected
   deletion boundary, risk, decision already known, and stop condition. If the audit
   finds no safe batch, say so plainly.

## Verification

This is a documentation and source-inventory change. Do not run test suites merely to
produce a pass count.

```powershell
py tools/size_report.py
rg -n "@router\.(get|post)|include_router|TemplateResponse|href=|src=|legacy|compatibility" api/webui api/operation_ledger
git diff --check
git status --short
```

Self-check the new map against each referenced module map and route owner. Confirm that
every retirement candidate has both a stated replacement and caller evidence. No
rendered browser verification is required because this brief must not change runtime
behavior.

## Stop conditions

Stop with RED rather than guessing if:

- A purported legacy surface has a live caller but no agreed canonical replacement.
- The canonical flow differs between current module maps, routes, and templates in a
  way that cannot be resolved from source.
- A candidate touches Canvas writes, grades/comments, credentials, student data,
  scheduled execution, or external AI transmission and the required safety boundary
  cannot be stated precisely.
- Completing the inventory would require reading private workspace data, making a live
  Canvas/API request, or editing runtime behavior.
- More than three independent retirement batches are needed to express the result;
  report the inventory and ask the senior to prioritize rather than manufacturing a
  mega-cleanup.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them
to the senior. Do not leave the only copy of execution state or evidence in chat.

### Execution result

- Traffic light: **GREEN**
- Commit hash: uncommitted (documentation-only change)
- Files changed:
  - `docs/reference/workbench-canonical-flow-map.md` (new)
- Verification commands and results:
  - `py tools/size_report.py` — clean, no unexpected large files
  - `rg -n "@router\.(get|post)|include_router|TemplateResponse|href=|src=|legacy|compatibility" api/webui api/operation_ledger` — confirmed route surface, template references, and legacy/compatibility markers; all findings incorporated into the map
  - `git diff --check` — clean (no whitespace errors)
  - `git status --short` — one new untracked file: `docs/reference/workbench-canonical-flow-map.md`
- Canonical flows mapped: 8 of 8 teacher outcomes mapped to entry points, templates, browser owners, backend owners, contracts, and safety boundaries
- Retirement candidates and recommended next batch:
  - **Batch 1 (needs product decision):** Legacy roster tier-scheme endpoints (`GET/POST /api/roster/tier-scheme`) — zero browser/template callers, but the underlying `get_roster_tier_scheme()` config function is live: PowerGrader (`powergrader.py:294`, `powergrader_late.py:40`, `routines_powergrader.py:177`) calls `roster_tier_by_id()` which depends on it. Endpoints can be removed; config data must stay.
  - **Batch 2 (MEDIUM – investigation gate):** Legacy QuizForge streaming routes (4 GET routes) — zero browser callers confirmed by existing test contract, but CLI consumer audit required before deletion.
  - **Reclassified as retained:** `GET/POST /api/tier-tags` — active Settings consumer found: `settings.html` inline JS calls `fetch("/api/tier-tags")` on save; `pages.py:254` supplies `tier_tags` template data. This is a live Settings feature, not legacy overlap.
- Deviations from the brief: None. Revised after senior review: tier-tags reclassified as retained (active Settings consumer found in `settings.html` inline JS and `pages.py` template data); tier-scheme reclassified from "ready to delete" to "needs product decision" after tracing `roster_tier_by_id()` callers through PowerGrader (`powergrader.py:294`, `powergrader_late.py:40`, `routines_powergrader.py:177`).
- Remaining blocker or decision: Batch 3 requires a CLI/external-tool consumer audit before any deletion can proceed. The four streaming routes are confirmed to have zero browser callers but may be used by `api/qf_pusher.py` or external scripts.
