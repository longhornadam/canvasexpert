# Execution brief: Roster Workbench lenses over one student dataset

Status: **ready for implementation**

Risk: **high** — the page contains private student data and controls existing Canvas
group mutations. Backend authority and mutation semantics are frozen.

Executor: **Luna**, with RED escalation rather than architectural guessing

## Outcome

Turn `/roster` into a coherent Workbench where a teacher selects one course, then works
through focused lenses instead of one overwhelming nine-column table. The lenses are
Students, Accommodations, Groups, Monitoring, Issues, and Privacy. They are views over the
same loaded roster and existing controls—not new workflows or state owners.

At ordinary laptop widths, each lens shows only the columns and bulk actions relevant to
that task. At narrow widths, the rail and toolbar stack cleanly while the roster table keeps
deliberate internal horizontal scrolling. Existing inline edits, group creation, labels,
bulk actions, privacy tools, and deep links continue to use their current backend paths.

## Locked decisions

1. **One dataset and one mutation path.** `api/webui/static/roster.js` remains the shared
   roster/course state owner. Existing feature modules and backend routes remain authoritative.
   Do not add another roster fetch, form, copy of student state, or Canvas write path.
2. **Filters own lenses.** `api/webui/static/roster/filters.js` remains the row-filter
   authority and expands slightly to own visual-lens selection and deep-link mapping. Do not
   add a second lens module or generic navigation framework.
3. **Use the existing filter buttons as the Workbench rail.** Move, do not duplicate, the
   existing `.roster-filter-btn` elements:
   - Students -> `all`
   - Accommodations -> `extra_time`
   - Groups -> `group_unset` (label it clearly as students needing placement)
   - Monitoring -> `monitored`
   - Issues -> `warnings`
   Privacy is one additional rail button that opens the existing safety tools and does not
   create a second row filter.
4. **Lens-specific presentation is CSS, not new data.** Set one `data-roster-lens` value on
   the Workbench shell. Use it to show relevant columns/panels/bulk controls. Preserve all
   current DOM IDs and inputs so existing feature modules remain owners.
5. **Shared Workbench composition.** `roster.html` extends `workbench_base.html`, uses the
   shared header/readiness strip, and loads a small page-specific stylesheet and existing
   scripts through `head_extra` / `workbench_scripts` exactly once.
6. **No new backend or persistence work.** Do not edit roster routes/helpers, config/vault
   formats, operation ledger, work registry, receipts, or group-operation adapters.
7. **No safety-semantic changes.** Inline local edits remain immediate/debounced as today.
   Canvas group create/membership actions keep their existing confirmation and route behavior.
   Privacy exports/backups remain local PRIVATE operations. Do not add auto-save or auto-apply.
8. **No private evidence.** Never commit or print student names/IDs, notes, groups, grades,
   course-derived values, screenshots, browser snapshots, or private paths.

## Scope

- `api/webui/templates/roster.html`
- New `api/webui/static/roster_workbench.css`
- `api/webui/static/roster.js` only to remove its duplicate query-focus ownership and expose
  any minimal existing-state hook required by `filters.js`
- `api/webui/static/roster/filters.js`
- `api/webui/static/roster/bulk.js` only if wrappers/hooks are required to keep its existing
  controls synchronized after template composition; do not change mutation behavior
- `api/tests/test_webui_template_contracts.py`
- `api/tests/test_roster_routes.py` only if an existing focused contract needs correction;
  do not add backend behavior for the UI
- `docs/reference/roster-module-map.md`
- `docs/reference/operation-ledger-release-status.md` status/path update at closure

The existing Roster CSS block in `api/webui/static/style.css` stays in place. The new
stylesheet contains only Workbench/lens/responsive composition overrides; do not turn this
batch into a global stylesheet extraction.

## Out of scope

- New roster endpoints, summary payloads, persistence fields, or migrations
- Operation-ledger/work-registry integration
- Rewriting table rendering, inline editing, group state, group creation, bulk mutation, or
  privacy feature modules
- Changing selected Canvas group-set authority or group membership semantics
- Changing pseudonymization, protected-name, who-is-who, or vault behavior
- New dialogs, client-side stores, tables, mobile card renderers, or duplicate forms
- Live Canvas writes, safety-tool exports/backups, scrub submissions, or local student-data
  fixtures committed to the repository

## Reference pattern and routing

- Shared shell: `api/webui/templates/workbench_base.html`
- Workbench composition: `api/webui/templates/gradebook.html`
- Successful session/work rail treatment: current PowerGrader templates and
  `api/webui/static/powergrader_setup.css` (composition only)
- Roster ownership and load order: `docs/reference/roster-module-map.md`
- Shared roster state: `api/webui/static/roster.js`
- Row filtering/deep link: `api/webui/static/roster/filters.js`
- Table DOM/columns: `api/webui/static/roster/table.js`
- Bulk controls: `api/webui/static/roster/bulk.js`
- Group panels: `api/webui/static/roster/group_state.js` and `groups.js`
- Privacy tools: `api/webui/static/roster/safety.js`
- Focused backend oracle: `api/tests/test_roster_routes.py`
- Existing template contracts: `api/tests/test_webui_template_contracts.py`

Read project-local `TOOLS.md` before broad inspection. The archived 13d3 handoff is
historical; this brief supersedes it.

## Implementation requirements

### 1. Compose the shared Workbench shell

- Change `roster.html` to extend `workbench_base.html`; use compatible body/main classes.
- Load `roster_workbench.css` in `head_extra` and the eight existing roster scripts in
  `workbench_scripts`, exactly once and in the current order.
- Add a `ce-workbench-shell` / two-column Workbench grid with:
  - a compact left rail containing the five moved filter buttons plus Privacy;
  - one main area containing the existing intro, course scope, summary, search, contextual
    panels, bulk bar, and single roster table.
- Remove the old shortcut links and toolbar filter-button container after moving those same
  filter buttons into the rail. Do not duplicate them.
- Keep every current form control and DOM ID used by Roster modules.

### 2. Make `filters.js` the single visual-lens authority

- Keep its current search and row-filter behavior.
- On lens change, set the shell's `data-roster-lens` and the active rail state, then call the
  existing filter/render seam once.
- Map deep links:
  - `?focus=extra-time` -> Accommodations
  - `?focus=groups` -> Groups
  - `?focus=monitoring` -> Monitoring
  - `?focus=issues` -> Issues
  - `?focus=privacy` -> Privacy
  Unknown/empty focus -> Students.
- Update the URL with `history.replaceState` when a teacher chooses a lens, without reload.
- Groups opens/focuses the existing group builder and exposes the existing group-label editor
  after course load. Privacy opens/focuses the existing safety details after course load.
- Privacy hides the roster table/bulk bar visually but does not clear loaded roster state.
- Remove `focusTarget`, scrolling, and `applyFocusTarget` ownership from `roster.js` so query
  focus has exactly one browser owner. Use the existing course-load hook for post-load focus.

### 3. Show only relevant controls without removing them

Use shell data attributes and CSS selectors; do not rebuild table rows.

- **Students:** show the full current table and all existing bulk groups.
- **Accommodations:** show selection, Student, Extra time, and Status columns; show only
  extra-time bulk controls.
- **Groups:** show selection, Student, Canvas group, and Status columns; show only group bulk
  controls; show/open group-set picker, group builder, and group-label editor.
- **Monitoring:** show selection, Student, Monitor, Note, and Status columns; show only
  monitoring bulk controls.
- **Issues:** show the full table so the teacher can resolve any warning type; show all bulk
  groups.
- **Privacy:** show/open the existing AI safety tools; hide table, search, and bulk controls.

Add small semantic wrappers around existing bulk-control clusters if CSS cannot target them
reliably. Preserve every button/input ID, `data-bulk` value, and event owner.

### 4. Responsive behavior

- Desktop/laptop: keep a stable left rail and wide main area. The roster table owns its
  intentional horizontal scrolling; the page itself must not overflow horizontally.
- At `900px` and below: stack the rail above the main area as a wrapping horizontal lens bar.
- At `760px` and below: stack course/search/summary controls without clipping; keep table
  scrolling inside `#roster-table-card` rather than inventing mobile cards.
- Provide visible active/focus states in both themes and preserve keyboard access to every
  lens and control.

### 5. Keep verification and documentation lean

- Add narrow template assertions for Workbench inheritance, page stylesheet placement,
  unique script order, rail/lens presence, and preservation of critical IDs.
- Add a focused browser-source assertion only if needed to lock single focus ownership; do
  not create CSS snapshots or duplicate route tests.
- Update `docs/reference/roster-module-map.md` with Workbench inheritance, new stylesheet,
  filter/lens ownership, deep links, load order, and current sizes for touched files.
- At GREEN closure, move this handoff into `docs/handoffs/archive/` and update
  `docs/reference/operation-ledger-release-status.md` to mark the Roster frontend batch
  completed. Do this in the implementation commit, not a second archive commit.

## Verification

```powershell
node --check api/webui/static/roster.js
node --check api/webui/static/roster/filters.js
node --check api/webui/static/roster/bulk.js
py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_roster_routes.py
git diff --check
```

No full API or engine suite is required because backend and engine behavior are unchanged.

Rendered verification uses the lifespan-disabled local server and a configured course only
for read-only roster loading:

```powershell
cd api
py -m uvicorn webui.server:app --host 127.0.0.1 --port 8765 --lifespan off
```

Check `/roster` at approximately `1366x768` light and `760x900` dark:

- shared Workbench header/readiness and one script copy in dependency order;
- no page-level horizontal overflow before or after a course loads;
- each lens activates, updates the focus query, uses the expected existing filter, and shows
  only its specified columns/panels/bulk controls;
- the table remains the only roster renderer and owns any horizontal scroll;
- deep links for extra-time, groups, monitoring, issues, and privacy select the same lenses;
- zero new console warnings/errors.

Use only structural counts/state in evidence. Do not print or capture roster rows, student
names/IDs, group names, notes, or screenshots. Selecting a course for a read-only Canvas GET
is allowed; do not change any input, selection, group, monitoring state, protected names,
scrub text, or export/backup action.

## Stop conditions

Stop with RED rather than guessing if:

- Workbench composition requires changing `base.html`, `workbench_base.html`, shared CSS, or
  another route.
- A lens requires a second roster dataset, renderer, state store, or form.
- Existing filter buttons/data values or named DOM IDs do not exist.
- Group/Privacy panels cannot be focused without changing their backend or feature ownership.
- Any mutation listener, `data-bulk` action, inline-save path, group authority, or privacy
  behavior must change to complete the layout.
- Verification requires a Canvas write, export/backup, scrub submission, or committed PII.
- A regression outside the authorized frontend composition blocks completion.

## Return report

Before handback, record the result here as well as reporting it to the senior.

### Execution result

- Traffic light: **not started**
- Commit hash: **not started**
- Files changed: **not started**
- Verification commands and counts: **not started**
- Rendered routes/viewports/lenses: **not started**
- Deviations from the brief: **none**
- Remaining blocker or decision: **none**
