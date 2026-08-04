# Direct execution brief: defaults + readiness, Batch 5 (A7, D4)

**Status:** Retired — GREEN; accepted 2026-08-03

**Executor:** senior (self-executed this session)

**Senior objective:** Promote Batch 5 of
`docs/handoffs/senior level/feature-freeze-hardening-initiative.md` (baseline
`dev` @ `b9da17d`, `api/tests` 2157 passed) — the last batch in scope for
this freeze-week cycle. Land A7 (default the Assessments pseudonymization
checkbox to checked, and explain plainly when a run keeps real names) and
D4 (a Home readiness card naming the unmet precondition when there are no
active courses and/or no school calendar, linking to the page that fixes
each). Batch C is explicitly NOT promoted after this — see the initiative
document's own recommendation (§9, "last: C") and §10 item 4.

## Required context

Read `AGENTS.md`, then §3 A7, §6 D4, §7, and §8 of the initiative document.

## Baseline re-verification performed this session

- `api/webui/templates/assessments.html:13`'s checkbox confirmed still
  unchecked by default; `api/dataforge/views.py`'s gating logic (now at a
  slightly shifted line range after Batch 3's `operational_log.emit` calls
  landed) confirmed unchanged: an un-anonymized run still writes reports
  only into the private `Student Work/Reports/DataForge` wall, still skips
  `history_store.save_snapshot` and `profile_export.publish_profile`.
- Traced the actual "results view" for A7's second half: `Render("results.html",
  ...)` in `dataforge/views.py::results()` maps to
  `api/webui/templates/assessment_results.html` via
  `api/webui/routes/assessments.py::_TEMPLATES`. `anonymized` was already
  in that render's context, so no new plumbing was needed beyond the
  template itself.
- Confirmed the exact "same voice" text D4 asks for:
  `gradebook.html`'s existing `{% if calendar_status != "ready" %}` block
  ("No school calendar configured — every day counts as instructional
  until one is set up. Set up Calendar…") and its source,
  `school_calendar.readiness()["status"]`, computed in the same
  `pages.py` route file as `dashboard()`.

## Locked decisions

**A7.** Add `checked` to the checkbox attribute (no JS, no default-value
plumbing — a static HTML default). In `assessment_results.html`, add one
`notice("attention")` block, shown only when `not anonymized and results`
(guarding against the page's own existing "no results" empty-state case),
naming both consequences (no history, no profile) and the reason (real
names were kept, both features need stable pseudonyms), plus the private
Student Work location where reports still landed and how to opt in next
run. Do not touch `assessment_dashboard.html` — the initiative document
says "results view," not the run's later Dashboard view.

**D4.** One readiness card on `dashboard.html`, shown when `active_count ==
0 or calendar_status != "ready"`, reusing the shared `notice()` macro (not
new page-specific CSS) and, for the calendar line, the exact existing
Gradebook wording verbatim rather than a paraphrase. The no-courses line
explicitly names Calendar and Create as the two things that work without
one this week, per the initiative document's specific emphasis. Computed
in the existing `dashboard()` route in `api/webui/routes/pages.py`
(`school_calendar` was already imported in that file for the Gradebook
route).

## Authorized scope and insertion points

- `api/webui/templates/assessments.html`,
  `api/webui/templates/assessment_results.html`,
  `api/tests/webui/routes/test_assessments.py`.
- `api/webui/routes/pages.py` (`dashboard()` only),
  `api/webui/templates/dashboard.html`, `api/tests/test_desk_routes.py`.

## Acceptance criteria

1. Loading `/assessments` shows the pseudonymization checkbox checked by
   default.
2. A results page rendered with `anonymized=False` and non-empty `results`
   shows the explanatory notice; `anonymized=True` (or empty `results`)
   shows nothing extra.
3. Home shows the readiness card's course line when there are no active
   courses, the calendar line when the calendar isn't ready, both when
   both are true, and neither when both preconditions are met.
4. Rendered verification against the real local workspace (currently: a
   configured Canvas token, no active courses, no school calendar) shows
   both readiness lines and zero console/server errors; `/assessments`
   shows the checkbox checked via `element.checked`, not just the markup
   attribute.

## Named verification gate

```powershell
py -m pytest api/tests/webui/routes/test_assessments.py api/tests/test_desk_routes.py api/tests/test_presentation_contracts.py api/tests/test_webui_template_contracts.py api/tests/dataforge -p no:randomly
```

Then the full gate: `py -m pytest api/tests -q`. Baseline 2157 passed.

## Stop conditions

Stop and report YELLOW/RED without guessing if: an un-anonymized run can
legitimately reach the results page with `anonymized=True` but zero
snapshots for a reason other than "no results were produced" (would make
the new notice's absence misleading); or `school_calendar.readiness()`
needs a workspace/root argument this route doesn't already have access to
(it doesn't — confirmed the same no-argument call `gradebook_page` already
uses).

## Execution result

Traffic light: GREEN

Commit hash: recorded in the commit that includes this brief.

Implemented exactly per the locked decisions. Verified live against the
real local workspace (token configured, no active courses, no school
calendar — precisely the blind-spot scenario §D4 describes): Home shows
both readiness lines with zero console errors, and `/assessments`'s
checkbox is checked (`element.checked === true`, not just the markup
attribute) with zero console errors.

Changed files:

- `api/webui/templates/assessments.html`,
  `api/webui/templates/assessment_results.html`
- `api/webui/routes/pages.py`, `api/webui/templates/dashboard.html`
- `api/tests/webui/routes/test_assessments.py` (+4 tests),
  `api/tests/test_desk_routes.py` (+2 tests)
- this brief

Verification:

- Focused gate (`test_assessments.py test_desk_routes.py
  test_presentation_contracts.py test_webui_template_contracts.py
  dataforge/ -p no:randomly`): 214 passed.
- Full gate (`py -m pytest api/tests -q`): 2162 passed (baseline 2157 + 5
  new tests, 0 removed).
- Rendered verification in the browser preview against the real local
  workspace: `/assessments`'s anonymize checkbox confirmed checked via
  `document.querySelectorAll('input[type=checkbox]')` (not just reading
  markup); Home shows "No active courses yet — most of Canvas Expert needs
  one to work with... Calendar and Create... both work without one" and
  "No school calendar configured — every day counts as instructional until
  one is set up," matching the real machine's actual unmet preconditions.
  Zero console/server errors on both routes.

Deviations: none.

Unresolved decisions: none for this brief. A5, D1.4, and 2.3 remain open
per the initiative document's §10 for a future senior review — none of
them block or are advanced by this batch. **Batch C is deliberately not
promoted after this batch**, per the initiative document's own
recommendation; this closes the freeze-week cycle's planned sequence
(§9 rows 1-5).
