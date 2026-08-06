# Three-scenario teacher trace: where CanvasExpert gets in the way

**Status:** Senior context. Diagnostic trace only; this document authorizes no implementation.

**Baseline:** `dev` @ `1847615`, `v1.0.0-beta.3`. Read from the working tree, which carries
uncommitted changes across Panels, Calendar, PowerGrader, and the MCP tools. `docs/handoffs/`
was emptied earlier this session, so this starts a fresh cycle.

**Method:** three scenario traces across UI and code, adversarially re-verified where a finding
was high-stakes. Confidence is tagged per finding (§2); §10 lists what's still unchecked.

---

## 1. Why this trace exists

The three scenarios are not feature requests. They are trust probes, and they are ordered the
way a real teacher would meet them:

1. Can CE describe my world back to me correctly, before I rely on it?
2. Can it help me author curriculum without writing something I did not approve?
3. Can it help me act on student data without leaking it or touching Canvas?

Each scenario ends with a boundary statement ("don't make Canvas changes unless I approve",
"show me the artifact before anything is written", "do not message students, post grades, or
write to Canvas"). Those boundaries are the actual subject of the trace. The finding that
matters most in this document is that one of them is not where the docs say it is — see §9.1.

---

## 2. Confidence tags

- **[V]** Adversarially verified: a reviewer tried to refute it and failed, or every hop was
  read directly.
- **[T]** Traced, not adversarially verified: grounded in a file:line read, but no refutation
  pass ran. Treat as a lead, not a fact.
- **[X]** Rests on something outside the repo (usually Canvas's real response shape).

---

## 3. Scenario 1: "I need my teaching day to run cleanly"

### 3.1 The blocking one: a fail-closed error that names a screen nobody built [FIXED 2026-08-06]

`_VAULT_CONFLICT_ERROR` at `api/mcp_server/tools.py:574-577` reads:

> identity vault conflict detected — resolve in the CanvasExpert web UI before pseudonymized
> reads continue

It guards nine call sites through `_open_vault()` (`tools.py:393, 1225, 1468, 1672, 1908,
1942, 2053, 2129, 2186`), which is every pseudonymized read: `get_roster`, `get_submissions`,
`get_gradebook_snapshot`, `get_seating_context`, `get_scoring_packet`. Detection is a
filename scan for `vault*.json` siblings (`api/feedback_vault.py:62-83`), so OneDrive forking
`vault.json` on a second machine is enough to trip it.

The backend already carries the conflict: `/api/mirror/status` returns it
(`api/webui/mirror_service.py:377`) and so does `/api/names/roster`
(`api/webui/routes/names.py:47,53`). Nothing renders either. Grep for
`vault_conflict|vaultConflict` across all `.js` and `.html` returns zero hits.

The teacher's whole assistant goes dark at once, the error tells them to fix it in the web UI,
and the web UI has no such screen. Home shows sync age, `/roster` offers "Back up vault",
`/settings` lists course freshness, `/connections` says `Canvas: Configured`. Nothing names
the vault.

Worth noting the asymmetry: the same class of problem *is* surfaced for catalogs, at
`api/webui/static/powergrader/setup_core.js:301` ("A competing OneDrive catalog copy needs
review."). The pattern exists and was never built for the identity vault.

**Fixed 2026-08-06.** That catalog "pattern" turned out to be thinner than it reads here on
first pass: it is a passive warning sentence appended to a status string, with no interactive
resolution at all, so porting it 1:1 would not have closed this finding (a teacher who hits the
MCP error is in their AI chat, not browsing the WebUI, and a sentence buried in a status line
they'd have to already be looking at doesn't reach them). Built instead: a real section on the
Students page (`roster.html`, id `roster-vault-conflict`), hidden unless a conflict exists,
fed by a new `GET /api/names/vault-conflict` (filenames, modified time, size — never vault
contents), with an "Open Identity Vault folder" button using the app's existing global
`data-open-path` handler. The app still never auto-merges or auto-picks a winner, consistent
with `feedback_vault.py`'s own design comment on why not; the fix is disclosure and a real
place to go, not automated reconciliation. `_VAULT_CONFLICT_ERROR` now names the Students page
by name instead of the generic "the CanvasExpert web UI." Verified live against a real
OneDrive-shaped conflict file on the machine this was built on (created, confirmed the section
renders with correct filename/timestamp/open-path, removed).

### 3.2 "Is my connection healthy" has three answers and the honest one is unwired [readiness.py half FIXED 2026-08-06]

- `/connections` renders `Canvas: Configured` from `bool(base_url) and token_is_set()`
  (`api/diagnostics.py:28-32`, template `connections.html:95-97`). No network call. A revoked
  token reads as configured. The container's `aria-label="MCP server health"` frames a
  credential-presence check as a health check, which is the misleading part; the word
  "Configured" is literally true.
- `POST /settings/test-connection` (`api/webui/routes/settings.py:213-237`) is a real probe,
  but it uses a bare `requests.get` and returns `str(e)` or `f"HTTP {r.status_code}:
  {r.text[:300]}"`. The teacher sees a raw resolver error or up to 300 characters of Canvas
  JSON. `api/webui/static/welcome.js:236-237` shows the same text with no prefix during
  first run. **Not touched** — still returns raw provider text on first run.
- ~~`api/webui/readiness.py` is the module that actually classifies `unauthorized` / `timeout`
  / `network`. It has no template or JS consumer, and stronger than that: nothing ever calls
  `readiness.probe()`, so `_LAST_PROBE` stays `None` and `snapshot()` returns every component
  as `{"status": "unknown"}`. The module is not merely unrendered, it never runs.~~ **Fixed.**
  `routines.py`'s existing 30-min heartbeat (`_routines_heartbeat`) now calls
  `readiness.probe(force=True)` every tick, so `_LAST_PROBE` gets populated ~90s after launch
  and refreshed every 30 min from then on. `/connections`'s Canvas line now reads
  `readiness.snapshot()` first, falling back to the old credential-presence text only in the
  unlikely window before the first tick. Its CSS still lives on at
  `api/webui/static/ui/layouts.css:16-17` unused (cosmetic, left alone). Both routes are
  pinned by `api/tests/test_route_contract.py:211-212`.

### 3.3 A requested sync that fails completely reports success [FIXED 2026-08-06]

`api/webui/static/desk.js:308` treats `plan.state === "failed"` as a normal terminal state and
resolves rather than throwing, so a "Sync now" whose every pass 401s walks through
`Syncing Canvas data… 0/6 scopes complete` and lands back on `Canvas data synced 3 days ago`.
No error is ever shown for a sync the teacher explicitly asked for.

The underlying `error_code` is specific and available: `api/mirror/store.py:1157-1159` sets
`auth_failed` via `api/mirror/sync.py:358` and `api/course_catalog.py:453-454`. Both
consumers drop it, reading only `last_success_at` (`api/webui/routes/pages.py:342-350`,
`desk.js:253-282`).

With no successful sync ever, Home says "Canvas data not synced yet," which is honest. The
misleading age only appears after a token that used to work stops working.

**Fixed 2026-08-06.** The specific `error_code` was computed server-side but never reached the
coordinator's job view: `_Job` in `api/mirror/coordinator.py` only recorded a generic
`error_class` (always `"acquisition_failed"` in practice, since the real runners never set that
key), never the actual code. Added a proper `error_code` field, threaded through from each
runner's `{"ok": False, "error_code": ...}` return. `desk.js`'s sync click handler now checks
`plan.state === "failed"` explicitly, maps the failed job's `error_code` to a plain-language
message (token/auth, forbidden, not-found, or a generic fallback), and stops before the
work-scan/reload chain can overwrite it with the stale success-shaped summary. Verified live in
the browser via a mocked fetch response, both the specific and fallback message paths.

### 3.4 "Is my teacher schedule complete" [V]

`_compose_readiness` (`api/webui/schedule_setup.py:91`) computes readiness as
`bool(teacher_schedule) and bool(bell_schedules)`. `teacher_schedule` is the parsed dict, so
`{"version":"1.0-json","blocks":[]}` yields `ready: True, count: 0`. There is no
all-periods-assigned check and no every-block-has-a-course check.

It does not matter much, because the payload has no consumer: `ready`, `missing`, `problems`,
and `unknown_course_ids` reach only `GET /api/schedule`, and the frontend calls only the POST.

A corrupt `Teacher Schedule.json` renders as "No blocks yet. Add a block to get started."
`routes/calendar.py` returns `teacher_schedule.problems`; `static/pages/calendar.js:889` reads
only `.blocks`. A teacher can retype a whole schedule over a file they believe is missing, and
only then hit "could not read Teacher Schedule.json" on save.

The app does warn about incompleteness, but only per block, at class time, on the classroom
projector: `api/webui/routes/panels.py:183` emits `f"No Canvas course linked to {name}."`
where `name` is the block's **label**, not its name (`panels.py:177`). With the shipped
template's placeholder intact, the wall reads "No Canvas course linked to Replace with your
class name." in front of students. Nothing aggregates this into "3 of your 6 blocks have no
course" beforehand, and Home never mentions the teacher schedule at all
(`_calendar_home_warnings`, `routes/pages.py:58-124`, covers only school-calendar readiness).

### 3.5 "Do today's classes line up with the bell schedule" has no page [V]

`deps.resolve_schedule_for` is the only function that joins bell schedule against teacher
schedule, and it has two non-test callers: MCP `get_day_schedule`
(`api/mcp_server/tools.py:2308`) and `resolve_panel_course`
(`api/webui/routes/panels.py:253`).

No WebUI page lists the resolved day. `/calendar` shows the day kind and the bell schedule
name ("Ready. School year 2026-27, coverage … Today: Exam Review Day.") and separately prints
every period with its times, but never joins them to the teacher's blocks. A Panel does show
one resolved block at a time, which is the only surface that does this join at all.

The silent-drop behavior in `resolve_day` is a real feature, not a bug: A/B rotation works
*because* a block whose periods are absent today vanishes without a problem, and
`api/tests/test_schedule_fixture.py:83-94` asserts exactly that against disjoint Day A / Day B
fixtures. The cost is that a CSV hand-edit is indistinguishable from correct behavior. Renaming
a period from `5` to `5th` in the Calendars folder, which is the officially recommended edit
path (`templates/calendar.html:276`), silences every Panel bound to that class on those days
while `/calendar` still shows green and cheerfully lists `5th 12:48 PM–1:38 PM`.

A typo entered through the Calendar editor is caught and named precisely, so the realistic
failure mode is the CSV hand-edit, not the form.

### 3.6 Panels: the requested panel exists, and eight others lag the bell [V]

`whats-due` is already "next class plus what is due": `resolve_panel_course` picks the block
meeting now, else the next block today, and the template prefixes "Next · ". It never displays
`next_change`, though, so the wall never says *when* the next class starts.

Only 1 of 9 panel templates implements the bell-boundary refresh. Confirmed by grep:
`next_change_minutes|msUntilMinutes|atBoundary` matches `panel_whats_due.html` and nothing
else. The other eight run `setInterval(load, 15 * 60 * 1000)`, so `learning-objective`,
`missing-work`, `random-student`, `random-student-no-repeats`, and
`birthdays-celebrations` can hold the previous class's content on the wall for up to fifteen
minutes after the bell.

### 3.7 Course and section discovery [V for sections, T for the rest]

There is no standalone section list in the WebUI. Every section reference in the frontend
derives from per-student rows (`static/seating.js:126`, `static/roster/relationships.js:22-39`,
`static/roster/scores.js:50-75`), so a section with zero students is invisible, and a section
cross-listed in from another teacher's course is indistinguishable from your own.
`list_sections` is MCP-only and returns id plus name.

**[T]** Course discovery keeps only `{id, name}` from `state[]=available`, which means
concluded courses cannot be added, no term is ever stored or shown, and TA/Designer/Observer
enrollments are indistinguishable from Teacher (`api/mirror/course_context.py` keeps
`enrollment_state` and discards `type`/`role`). Needs the §10 re-check.

---

## 4. Scenario 2: "I want to align a unit before I teach it"

### 4.1 The evidence base is probably empty at the root [FIXED 2026-08-06, code-side]

`normalize_page` (`api/course_catalog.py`) opens with:

```
if not isinstance(row, dict) or not _id(row.get("id")):
    raise ValueError("page row has no stable id")
```

`_id(None)` returns `""`, which is falsy. Canvas's Pages index returns `page_id` and `url`;
the Page object has no `id`. Nothing remaps it: the fetch at `api/course_catalog.py:692` calls
`PAGES_PATH` with `{"per_page": 100, "include[]": "body"}` and hands rows straight to
`_page_scope_from_receipt`, which catches the `ValueError`, sets `invalid_membership`, and
returns `_incomplete_membership(..., "invalid_page_record", valid_records=[])`.

Two pieces of corroboration that Canvas really returns `page_id`/`url` here:

- The sibling adapter hits the **same endpoint** and uses `url` as the identifier throughout:
  `api/operation_ledger/adapters/page.py:95` reads `page.get("url")`, and `:199` takes
  `response.get("url")` as the `page_slug` after creating a page. It never reads `id`.
- The fixtures were written to match the parser rather than Canvas.
  `api/tests/mirror/test_read_service.py:8` is `def _page(page_id="p1", **changes)` and then
  assigns that value into the `"id"` key. The parameter name records what the author knew;
  the key records what the parser demanded. Every `/pages` stub in
  `api/tests/webui/routes/test_course_catalog.py` returns `[]`.

If this holds on a real course, the pages scope never reaches `state: "current"`,
`get_course_pages` returns nothing, and every page-based learning-objective source ref is
refused, because `source_records` requires `scope["state"] == "current"`. Scenario 2 asks the
assistant to judge whether objectives are "poorly supported by the course materials" while a
third of the materials may be structurally unreachable, and the failure presents as "this unit
has no pages" rather than as an error.

**Fixed 2026-08-06, code-side, still not exercised against a real course.** No live course
existed to make the one authenticated GET that would have proven this beyond code reading, so
the fix went in on the strength of the code-side analysis above plus the two corroborating
pieces of evidence: the sibling adapter's `url`-based identity and the fixtures that already
admitted, in their own parameter names, what Canvas actually sends. `normalize_page` now reads
`row.get("page_id")` instead of `row.get("id")`, both for the stable-id check and for the
normalized record's `id` field. The two test fixtures that had encoded the bug (`_page` in
`api/tests/mirror/test_read_service.py` assigning its `page_id` parameter into an `"id"` key,
and every `/pages` stub in `api/tests/webui/routes/test_course_catalog.py` returning `[]`) are
corrected: both files now build page rows shaped like real Canvas output, and
`test_course_catalog.py` gained a regression test that reverting the fix turns red (confirmed by
temporarily reverting it: without the fix, a course's first sync makes the pages scope
`"unavailable"`, not merely `"incomplete"` as originally guessed, because there is no previous
good state yet to fall back to).

This closes the code-side half of this finding. The Canvas-side half — whether `page_id` is
really the field, and whether anything else about real Pages responses differs from the
fixtures — still wants the first live sync this fall as final confirmation. That first sync is
now a lower-stakes check (does the fix hold) rather than a diagnostic for an open bug (is there a
bug at all).

### 4.2 The staleness verdict exists and the assistant cannot see it [V]

`list_learning_objectives` (`api/mcp_server/tools.py`) builds each row as:

```
entry["id"], entry["objective"], entry["effective_start"],
entry["effective_end"], [ref["title"] for ref in entry["source_refs"]],
entry["authored_at"],
```

That list comprehension takes `title` only. `kind` and `id` are dropped, and so are
`source_digest` and `catalog_updated_at`.

`changed_source` is the product's own answer to "is this objective outdated", and
`api/webui/panel_data.py` computes it as
`source_digest(catalog, entry["source_refs"]) != entry["source_digest"]`. Neither operand
survives the MCP projection. So the exact question the scenario opens with, which objectives
are outdated, is unanswerable from the assistant's side, and the assistant will fall back to
guessing from dates and titles.

The same omission blocks the revision: to call `preview_learning_objective(replaces=id)` the
assistant must rebuild `source_refs` with `kind` and `id`, reverse-engineered by matching
titles. A module and a page sharing a title are indistinguishable, and a renamed source is
unrecoverable.

### 4.3 The repair path points somewhere the teacher will not look [V]

`POST /api/course-catalog/refresh` has exactly one UI caller in the whole tree:
`api/webui/static/powergrader/setup_core.js:346`, behind "Sync course list" on the PowerGrader
setup rail. There is no catalog refresh on `/settings`, `/course`, `/panels`, or the dashboard,
and no MCP tool refreshes the catalog at all (`refresh_mirror` covers roster, assignments, and
submissions only). Meanwhile the panel's own repair copy says "No local course catalog yet.
Refresh it in CanvasExpert, then this panel fills in." All three catalog-reading tools say the
same thing back to the assistant: `get_course_pages`, `get_modules`, and
`get_course_assignments` all return, verbatim, "No local course catalog found for this course.
Refresh the catalog from the CanvasExpert web UI, then try again" when `scope["source"] ==
"none"` — an instruction the assistant itself cannot act on. `get_course_pages`'s own docstring
states this as policy, not oversight: "The refresh route is the only Canvas acquisition path.
This read never refreshes... or exposes the workspace path."

### 4.3a Decided: the assistant should trigger that refresh itself, the same way it does for the mirror

User's call: an assistant hitting stale or missing catalog data should behave exactly like it
already does on a stale mirror (`get_roster`, `get_submissions`, `get_gradebook_snapshot`)
refuse, call a refresh tool, retry once, rather than surface a dead-end instruction to relay to
the teacher. That needs one new MCP tool, `refresh_course_catalog(course_id)`, wrapping the
existing `POST /api/course-catalog/refresh` handler (`api/webui/routes/course_catalog.py:40`)
the same way `refresh_mirror` wraps the mirror sync. Once it exists, update the three refusal
messages in `get_course_pages`, `get_modules`, and `get_course_assignments` to name it (matching
the existing "call refresh_mirror(course_id), then retry that read once" pattern already in
`START HERE`), and add the same instruction to `START HERE`'s catalog-reading bullets.

This is buildable now, independent of having a live course, and it directly narrows what the
fall diagnostic in §4.1 needs to check: once this ships, "pages came back empty" only means one
thing (the assistant already retried after a fresh sync), instead of two indistinguishable
things (stale catalog vs. the suspected `id`/`page_id` bug).

Note the same caution already on file for `refresh_mirror` in §10 (25s timeout against a
sequentially paginated full pass, no progress signal) likely applies to a catalog refresh tool
too — it is a full sync of the same shape, not a new risk to separately verify.

### 4.4 "Show me the artifact before anything is written" is chat narration [T]

`learning_objective` sits in `_DIRECT_WRITE_CONTRACT_KINDS`, so `get_authoring_contract`
returns it without the staging appendix, and the write goes straight to
`Library/Panels/Learning Objectives.json`. It never appears in the "Staged by your assistant
(pending review)" tab and `list_staged_content` cannot see it. `preview["proposed"]` genuinely
is the byte-exact record that will be written and it is digest-protected, but there is no file
to open, no diff view, and no server-side record that a preview was ever shown. Needs §10
re-check, along with the revision-protection holes (apply never verifies the target still
matches `preview["outgoing"]`; the `revision` counter is global across courses;
`catalog_generation` churns on every refresh).

### 4.5 "Exact source references" cannot be as exact as asked [T]

`SOURCE_REF_KEYS` is `{kind, id, title}` and nothing else. There is no quoted-text field, no
offset into the cited body, no standards field, no rubric-criterion reference, and no page URL
ever, since URLs are replaced with `[link]` during normalization and `PAGE_KEYS` has no slug.
Verified directly: `PAGE_KEYS = {"id", "title", "body_text", "published", "front_page",
"updated_at"}` at `api/course_catalog.py:50`.

So the assistant can produce verified pointers (kind, id, title) and unverified prose (the
quotation, the TEKS code, the rationale). Everything a teacher would read *as* a citation sits
in the unverified half. Rubric criteria, which are the strongest available evidence for
"is this objective actually assessed", are persisted in the catalog and exposed by no tool.

### 4.6 "This unit" is not a thing [T]

There is no unit entity anywhere in the domain; a unit is a module naming convention. Worse
for this scenario, module items of type Page carry `content_id` while Canvas identifies page
items by `page_url`, so the module-to-page join appears to be unavailable and the assistant
would have to fuzzy-match titles. This shares a root cause with §4.1 and should be checked in
the same pass.

---

## 5. Scenario 3: "I need to act on a pattern in student progress"

### 5.1 The crux: the app already answers this better than the assistant can [V]

Both paths call the same pure aggregator, `api/gradebook_snapshot.py::build_snapshot`.

- Over MCP, `get_gradebook_snapshot` returns pseudonyms. The teacher gets a narrative about
  Sparky McGee and Nova Quill.
- Over the web UI, `GET /api/gradebook` returns real names. `build_snapshot` builds each
  student as `"name": s.get("sortable_name") or s.get("name", "")`, and the route strips only
  `user_id`.

And the app path does not even refuse when the mirror is stale. The route's `load_snapshot`
delegates to the shared loader with no `queries` override in production (the `RouteQueries`
seam only engages when the readers are monkeypatched for tests), so it is mirror-first with a
live-Canvas fallback. The MCP tool, by contrast, hard-refuses past six hours.

So the assistant's contribution is the pattern analysis, and its cost is that the names in
that analysis are unusable. There is no surface that takes a pseudonymized narrative and
re-identifies it; the re-identification paths that exist are structured and manual (the Roster
console row carrying name and pseudonym together, the `who-is-who.csv` export, and
PowerGrader's `reidentify`, which accepts only the scoring-row shape tied to one session).
The teacher's real route is to get a pseudonymized brief and hand-translate eight to fifteen
names.

This is the finding to design against, not a bug to patch. Decided in §9.2: the assistant keeps
producing the pseudonymized pattern narrative exactly as it does today; a new local-only utility
on the Roster page translates it back to real names for the teacher's own reading, without
routing real names through the assistant's path.

### 5.2 "Respecting accommodations" has one integer behind it [V]

Searched `api/` for `accommodat|iep|section_504|504_plan|modified_assignment` outside tests.
Two hits: `api/audience.py:62`, where `special_ed` and `section_504` are *audience kind
labels* for a filter and not fields on any student record, and a comment in
`api/student_packet.py:102`.

The only accommodation datum is `extra_time`, a plain list of `{id, name, days}` in synced
state (`api/webui/config/gradebook.py`). Days of grace, with no reason, category, date range,
or per-assignment scope. There is no IEP or 504 flag, no modified-assignment list, and no
alternate deadline per student per assignment.

**[T]** And the MCP `late` column is Canvas's raw boolean with no extra-time subtraction,
while the one accommodation-aware late computation
(`api/work_registry/providers/late_work.py`) carries no student identity and is not reachable
from MCP. School-day math has no MCP tool either, so an assistant computing lateness would
count weekends and holidays.

So the scenario's phrase "respecting accommodations" is representable only as "subtract N
school days before calling something late", and even that is unavailable on the path the
assistant would use. This deserves a plain product answer rather than a partial
implementation: say so in the product, or decide the grouping belongs in the app where the
extra-time math already lives.

### 5.3 Excused work is invisible, and two totals disagree [V]

`build_snapshot` skips excused submissions outright: `if not a or sub.get("excused"):
continue`. Excused work therefore counts toward nothing, in both the MCP tool and the WebUI
Gradebook page.

`ungraded` is CE-derived and sits in an `elif`, so a submission that is `graded` with a null
score counts as neither graded nor ungraded. And `total_ungraded` uses a different rule from
the per-student column: `sum(a["submitted"] - a["graded"] ...)` at the assignment level
against `submitted_at` plus `workflow_state` per student. The two numbers can disagree on the
same screen.

### 5.4 "Prepare a local weekly routine" has no home [scheduler bug FIXED 2026-08-06]

`_run_routines_bg` (`api/webui/routes/routines.py:248-252`) opens:

```
for rid, meta in _ROUTINE_DEFS.items():
    if not meta.get("custom"):
```

Custom routines are the only entries carrying that key (`routines.py:154-155`), so the
background loop runs built-ins only. The single caller is `_routines_heartbeat`
(`:237-245`). The other heartbeat is the mirror's and never touches `_ROUTINE_RUNNERS`. So a
custom routine fires only when someone clicks a button.

`api/webui/README.md:300-303` asserts the opposite, in as many words: "Custom routines get the
same three triggers (Run now / catch-up on launch / every 30 min) … no parallel path." No test
references `_run_routines_bg`, so the skip is uncovered.

What the teacher experiences: a custom routine renders identically to a built-in, with an
enable checkbox, an editable "Every [168] h" field, and a "due" chip. They tick it, leave the
app open all week, and the row still reads "Never run". Clicking "Run what is due" works,
which reinforces the wrong conclusion.

Three more constraints stack on top: no MCP tool can create, enable, run, or even report a
routine (confirmed against all 47 `@mcp.tool()` decorators); a new routine file needs an app
restart; and no routine can call an LLM, since the SDK exposes Canvas reads, calendar helpers,
and datetime but no AI client. CE is also not a persistent service, so nothing runs when the
app is closed.

The clean shape the scenario asks for is roughly 80% built and has no assembly point.

**Scheduler bug fixed 2026-08-06.** The README's claim was not aspirational, it was the
intended contract, and the `if not meta.get("custom")` line was the one place the code broke
it. Removed. Custom routines now run on the same heartbeat as built-ins; verified by reverting
the one-line fix and watching a new regression test go red (no test existed before this). The
other three constraints in this section (no MCP tool control, app-restart to add a routine, no
LLM access from a routine, no persistent service) are unrelated design boundaries, not bugs,
and are unchanged.

### 5.5 The write boundary, in the direction asked [V]

Messaging students is structurally impossible: the Canvas Conversations API is referenced
nowhere in the repo. Submission comments appear as reads, plus one outbound field on the
teacher-initiated grade push. `stage_scores` deliberately declines to trigger autopush.

The one real exception is roster `canvas_group` patches, which do write live Canvas group
memberships through this exact assistant path — see §9.1. It's a deliberate write, gated the
same way every other MCP write is gated, not a leak in this boundary. Worth naming here
because a reader of this scenario alone would otherwise conclude the boundary is absolute.

---

## 6. Cross-scenario collisions

- **Scenario 1 breaks Scenario 2.** A catalog refresh rewrites `catalog["updated_at"]`
  unconditionally, and `catalog_generation` is keyed on it, so any refresh invalidates a
  pending learning-objective preview. The refresh most likely to fire is the automatic one on
  PowerGrader course selection. A careful review conversation is the thing most likely to
  invalidate its own preview. **[T]**
- **A single OneDrive fork stops Scenarios 2 and 3 together.** §3.1's vault conflict
  fail-closes every pseudonymized read, and the repair screen does not exist. **[V]**
- **Scenario 1's own diagnostics are the least trustworthy surface in the app.** A teacher
  running the trust probe in order reads `Canvas: Configured`, clicks "Sync now", sees it
  succeed, and proceeds into Scenarios 2 and 3 on a revoked token. **[V]**

---

## 7. Asks with no surface at all

Worth stating plainly, because these are product answers rather than defects:

| Ask | Status |
|---|---|
| "whether today's classes line up with the bell schedule" | No page joins them. Panels and MCP only. **[V]** |
| "respecting … accommodations" | Was one integer of grace days, unreachable from MCP. Decided 2026-08-05, now batch 8 (§9.3). **[V]** |
| "teacher-only summary of which students need attention" | Real names exist in the app, never on the assistant's path. Decided 2026-08-05, now batch 9 (§9.2). **[V]** |
| "prepare a local weekly routine" | Custom routines do not fire on a schedule. **[V]** |
| "this unit's …" | No unit entity. **[T]** |
| "exact source references" | No quotation, offset, or URL is representable. **[T]** |

---

## 8. Recommended batch sequence

Sequenced by teacher cost and by what unblocks the most other work.

| # | Batch | Contents | Why here |
|---|---|---|---|
| 1 | Catalog self-refresh for the assistant | Add `refresh_course_catalog(course_id)` wrapping `POST /api/course-catalog/refresh` (§4.3a); point `get_course_pages`/`get_modules`/`get_course_assignments`'s refusal messages and `START HERE`'s catalog-reading bullets at it, mirroring the existing mirror refuse-refresh-retry pattern | No live course needed; buildable now. Turns "pages came back empty" into one diagnosable signal instead of two, ahead of the fall check in §4.1 |
| 2 | Vault conflict renderer | Render the `vault_conflict` payload already returned by `/api/mirror/status` and `/api/names/roster`; follow the catalog pattern at `setup_core.js:301` | Currently the only finding that dead-ends the assistant entirely with no repair path |
| 3 | Honest sync and connection status | Stop resolving `plan.state === "failed"` silently (`desk.js:308`); surface `error_code` on the two consumers that drop it; reuse `readiness.py`'s existing `_code()` classifier (not a new one) so `test-connection` stops printing resolver exceptions; wire `readiness.probe()`/`snapshot()` into `/connections`, replacing the naive `bool(base_url) and token_is_set()` check (§9.4) | Scenario 1 is the trust probe; it currently fails quietly |
| 4 | Custom routines fire on schedule | Fix the `if not meta.get("custom")` skip, add the missing test, and correct `api/webui/README.md:300-303` either way | A documented promise the code does not keep |
| 5 | MCP write disclosure and consistency | Correct the seven "never/cannot write to Canvas" sites in §9.1 (code, docs, and the in-app `/about` page), retire the stale `START HERE` copy so already-installed teachers actually get the fix, move "confirm with the teacher first" onto the `apply_*` description for every preview/apply pair, and add the missing `canvas_group` test | Decided; scope is disclosure and doc consistency, not new capability or new gating |
| 6 | Learning-objective projection | Carry `kind`, `id`, and `source_digest` through `list_learning_objectives` | Makes Scenario 2's opening question answerable at all. Independent of batch 1 now that batch 1 no longer requires a live course; can run in parallel |
| 7 | Bell-boundary refresh for the other eight panels | Send `next_change_minutes` and reuse the `whats_due` pattern | Known-good pattern, mechanical, visible in every classroom |
| 8 | Accommodation-aware lateness | Reuse `late_work.py`'s instructional-range and extra-time logic at the per-submission level; add `effective_late` to `get_gradebook_snapshot` alongside the existing raw `late` (§9.3) | Decided 2026-08-05; makes "late" mean something a teacher would actually call fair |
| 9 | Local name-reveal utility | Add a paste-and-reveal tool to the Roster page: client-side pseudonym-to-name substitution against the roster table already loaded there, no network call, nothing persisted (§9.2) | Decided 2026-08-05; closes the gap between what the assistant can say and what the teacher can act on, without weakening the pseudonym boundary |
| 10 | Delete the dead Name Manager endpoints | Remove `/api/names/roster`, `/nickname`, `/pseudonym`, `/pseudonym/regenerate`, `/collisions` and their tests; keep `/protected`, `/scrub-test`, `/who-is-who`, `/backup-vault` (§9.4); check whether `/name-manager`'s redirect route is still linked anywhere | Decided 2026-08-05; confirmed dead, not unfinished — the modern Roster Console already does these jobs a different way |

§9.2, §9.3, and §9.4 were open product decisions as of the first draft of this document; all
three were decided on 2026-08-05 and are now batches 8, 9, and 10 above (readiness.py's half of
§9.4 folded into batch 3 instead of its own batch), not backlog.

---

## 9. Open decisions

### 9.1 MCP Canvas write: decided, keep the capability, fix the disclosure everywhere it appears [FIXED 2026-08-06]

**All seven sites fixed 2026-08-06** using the exact suggested wording below: `__init__.py`,
`docs/mcp-server.md` (both the intro bullet and the `apply_roster_student_change` table row),
`about.html`, and all three `START HERE - CanvasAgent.txt` Appendix D lines (with the required
pre-edit hash added to `ai_ta.RETIRED_FILES` so a teacher's existing seeded copy gets
re-seeded), plus the `test_tools.py` docstring. Verified: full suite green, CORE line 37
confirmed untouched by construction (its wording is textually distinct from the Appendix D
lines edited).

`apply_roster_student_change` with a `canvas_group` patch writes real Canvas group
memberships. The chain is `api/mcp_server/tools.py:308` (`canvas_group` in
`_MCP_ROSTER_PATCH_KEYS`) through `roster_mcp.py:10`, `roster_updates.py`, `roster.py`,
`roster_canvas.py`, to `_canvas_send`, issuing a DELETE of the old membership and a POST of the
new one. In Canvas that reassigns group discussions, group submissions, and group grades.

**Decision: keep the capability, correct the disclosure.** This is not a special case that
needs new gating. It's the same digest-protected preview/apply pattern already used for
learning objectives and the school calendar, and the product already treats "confirm with the
teacher first" as sufficient consent for schedule writes that are equally live and equally
without a review queue. The fix is documentation and consistency, not new enforcement.

**The governing policy, stated plainly so it does not need re-deriving per tool:** Canvas
writes are not the norm here. Staging through CanvasExpert or PowerGrader for teacher review and
push is the norm, and stays the norm. A direct write is acceptable specifically when the teacher
tells the assistant to do it — `canvas_group` already fits that shape (digest-protected preview,
applied only on the exact reviewed patch), and any future direct-write tool should be held to
the same bar rather than to a blanket "never." The documentation fix in this batch is about
making that true state legible, not about deciding it for the first time.

**Every site carrying the false claim, swept across code, docs, tests, and the app's own UI
(not just the three found on the first pass):**

1. `api/mcp_server/__init__.py:9-10` — "this package never writes to Canvas and never binds a
   network port." Split the sentence: the network-port half stays true, the Canvas half does
   not. Suggested: "CanvasExpert keeps sole custody of the Canvas PAT and almost every write
   path — this package writes to Canvas only through one explicit, digest-protected roster tool
   (`canvas_group`), and never binds a network port."
2. `docs/mcp-server.md:7-9` — "writes nothing beyond the identity vault it already shares with
   the rest of CanvasExpert." Needs the same disclosure, plus a one-clause addition to the
   `apply_roster_student_change` table row (currently just "Applies the exact reviewed preview
   through the existing Roster mutation path") noting that a `canvas_group` patch reaches Canvas.
3. `api/webui/templates/about.html:95-97` — **teacher-facing, not internal docs.** "When an
   assistant connects over the local MCP server, it receives pseudonymized reads and can use
   preview/apply pairs for teacher-owned local changes. MCP never writes to Canvas." This is the
   app's own privacy/security page. A teacher reads this directly. Fix in the same spirit as the
   others: name the one exception plainly rather than deleting the reassurance wholesale — the
   rest of the page's claims (token never on disk in plaintext, accommodation data stays home,
   grade changes are preview-first) are true and should stay exactly as they are.
4. `START HERE - CanvasAgent.txt:225` (Appendix D opening) — "You cannot write to Canvas at
   all. Nothing you do here reaches students until the teacher pushes it themselves." Suggested:
   "With one exception below (a roster tool that reassigns a student's Canvas group membership),
   nothing you do here reaches Canvas directly; everything else reaches students only after the
   teacher pushes it themselves."
5. `START HERE - CanvasAgent.txt:287` (roster settings bullet) — "These are the teacher's own
   local settings, pseudonym-first, never Canvas membership." Suggested: "These are mostly the
   teacher's own local settings, pseudonym-first. One field is not local: `canvas_group`
   reassigns the student's real Canvas group membership immediately when applied, the same way
   the schedule tools below write live."
6. `START HERE - CanvasAgent.txt:309` (Appendix D close) — "You never write to Canvas. That line
   does not move." Suggested: "Outside that one roster exception, nothing above reaches Canvas on
   its own: everything else writes to the teacher's own computer, and the teacher is the one who
   pushes."
7. `api/tests/mcp_server/test_tools.py:1` — module docstring still reads "Offline tests for the
   read-only MCP server's tool implementations." The "read-only" framing was already ruled dead
   in [[mcp-doc-accuracy-sweep]]; this is a leftover. Drop the word.

**Deliberately not touched:** CORE block line 37 in `START HERE` ("The one hard line: you never
write to Canvas, even when your tools look able to. Asked to push, hand the draft over as ready
for their review.") stays as-is. It is scoped to the authoring/staging loop specifically (the
five numbered steps right above it are entirely about drafting content and staging it), it
remains true there, `test_the_never_push_rule_is_in_the_core` pins that exact phrase, and CORE is
hard-budgeted at 1500 characters for the ChatGPT custom-instructions box. Only Appendix D — the
section that actually lists `canvas_group` — carries the contradiction. Confirmed no test pins
the Appendix D wording, so items 4-6 are free to edit.

**Also swept and confirmed accurate, not paranoia — leave alone:** `api/ai_clients.py:20-21`
("never touches Canvas," but scoped to the local-AI-client config-merge module, unrelated to
MCP); `tools.py:1123`'s `_staging_appendix` ("You never write to Canvas," but only appended for
kinds that are genuinely staging-only, never for `canvas_group`); `docs/contracts/
feedback-scoring-contract.md:212`; `api/operation_ledger/catalog_reconcile.py:14`;
`api/webui/README.md:39-40`; `api/mcp_server/server.py:7` (stdio-only claim, still true);
`roster.html:237`, `about.html:114-116`, `panels.html:182`, `_routines_panel.html`,
`seating.js:613`, `write_review.js:59` — all narrow, true claims about something else entirely.

**A required step this batch cannot skip:** `START HERE - CanvasAgent.txt` is a seeded file —
`ai_ta._write_text_if_missing` never overwrites a teacher's existing copy, so editing the source
text alone does nothing for anyone who already has it. The fix only reaches them if the
currently-shipped file's hash (via `ai_ta._shipped_hash`, computed on the bytes *before* this
edit, normalized for line endings) is added to `ai_ta.RETIRED_FILES["START HERE -
CanvasAgent.txt"]`. Compute that hash first, make the text edits, then add the pre-edit hash to
the retired set — not the post-edit one, or `test_a_retired_name_that_still_ships_cannot_churn`
fails. This is exactly the mechanism [[canvasagent-instruction-set]] describes for the last
rename; it applies here even though the filename isn't changing, only the content.

**Adjacent, not part of this batch:** the mutation-ownership contract
(`docs/contracts/canvas-transport-owners.json`) has no `api/mcp_server` entry at all — it isn't
making a false claim, it's silent, for the same AST-literal-call-site reason noted in
[[mutation-contract-trust]]. Worth a future line item, not a blocker here. Also not in this
batch: op-log provenance (`api/webui/canvas_client.py:333` names the operational-log event from
the HTTP verb alone, so there's no on-disk record of whether a Canvas group change came from the
assistant or the teacher) — a real observability gap but a nice-to-have, see §9.4.

### 9.2 Missing/late/ungraded triage: decided, build a local-only translate view

§5.1's gap: the assistant produces a good pattern narrative but the names in it are unusable,
while the app's own Gradebook screen already has the same underlying data with real names
attached. Rejected: giving the assistant a re-identification tool — that would put real names
into the LLM's context, which is exactly what the vault exists to prevent. Decided instead:
build the reverse lookup entirely inside CE, client-side, on a page that already has both name
and pseudonym loaded together.

Shape: add a small utility to the Roster page, which already renders name+pseudonym rows for
every student (§5.1's "Roster console row carrying name and pseudonym together"). A textarea
where the teacher pastes the assistant's pseudonymized answer, and a button that does a
client-side find/replace of every recognized pseudonym against the real name from the roster
table already loaded on that page. No new backend endpoint should be needed if that page's
client-side data already carries both fields — confirm that first. Nothing is sent anywhere,
nothing is persisted, no LLM or network call is involved; the pasted text and the substitution
both stay inside the teacher's own browser session, which is what keeps this consistent with the
reason `get_gradebook_snapshot` pseudonymizes in the first place.

Two things for whoever builds this to check, not decided here: whether pseudonyms are unique
per-course or global across a teacher's workspace (determines whether the lookup needs a
`course_id` or can just use the currently-loaded roster), and whether to also surface this from
Home or only from Roster.

### 9.3 Respecting accommodations: decided, wire it up properly

§5.2's gap: the only accommodation datum is `extra_time` (grace days), and it is not applied to
the `late` field the assistant sees via `get_gradebook_snapshot` — that field is Canvas's raw
boolean (`gradebook_snapshot.py:40`, `if sub.get("late")`). The correct math already exists,
just not reachable from MCP or per-student: `api/work_registry/providers/late_work.py::scan_course`
already computes accommodation-aware lateness correctly, using
`school_calendar.resolve_instructional_range` for real school-day counting (excluding weekends
and holidays) and `config.get_extra_time` for grace days. It aggregates per-assignment and drops
which student, because it was built for a dashboard nudge, not a per-student query.

Rejected: giving the assistant raw calendar-math primitives and letting it compute this in
conversation (the "cheap middle ground" option) — that risks a confidently wrong answer with no
way for the teacher to catch it. Decided instead: reuse the same instructional-range and
extra-time logic `late_work.py` already has, at the per-submission level, and surface the result
as a new field on `get_gradebook_snapshot` (e.g. `effective_late`) alongside the existing raw
`late`, so nothing that already depends on `late`'s current meaning regresses.

Two design points to carry over from `late_work.py`'s existing pattern rather than reinvent:
(1) when `resolve_instructional_range` can't cover the needed date span, `late_work.py`
deliberately raises (`CalendarNeedsAttention`) rather than silently treating every day as
instructional — the new per-student path should fail the same way, flagging `effective_late` as
unavailable for that student/course rather than guessing; (2) the extra-time lookup and
school-day math both need the real `user_id`, so this has to run before pseudonymization, the
same ordering `build_snapshot` already uses today for its other fields.

### 9.4 Two live endpoints with no consumers: decided, one dead, one unfinished

**`GET /api/names/roster` and four siblings — dead, confirmed by more than absence of a
caller.** `names.py` is the API surface behind a retired screen: `api/webui/routes/pages.py:254`
has `GET /name-manager` whose entire body is `"""Old Name Manager — redirect to the new Roster
Console."""` followed by a 302 to `/roster`. The modern Roster Console
(`roster.html`/`inline_edit.js`) does the same jobs a different way — `inline_edit.js` sets
pseudonyms, nicknames, and pseudonym regeneration through the unified per-student PATCH path
(`roster_updates.update_student`, the same path `canvas_group` uses), not through `/api/names/*`.
The bulk "sync from Canvas, upsert into vault" operation `/api/names/roster` performs isn't
stranded either: `roster_service.upsert_roster` (the actual logic) is called live from
`api/webui/routes/roster.py`'s own route, plus from MCP tools and daily-writing ingest. Nothing
is uniquely reachable through `/api/names/roster`, `/nickname`, `/pseudonym`,
`/pseudonym/regenerate`, or `/collisions` — all four have zero callers outside tests. The other
four endpoints in the same file, `/protected`, `/scrub-test`, `/who-is-who`, `/backup-vault`, are
alive, called from `roster/safety.js`, and stay.

**Decision: delete the five dead endpoints and their tests; keep the four live ones.** Worth a
quick check while in there: whether anything still links to `/name-manager` itself, or whether
that redirect route can go too.

**`api/webui/readiness.py` — unfinished, decided to finish it, folded into batch 3.** Its
probing logic is real and correct: it checks whether the Canvas token actually works (not just
whether one is saved), whether the OpenRouter key validates, and whether the workspace is
writable, classified into `unauthorized`/`timeout`/`network`/`ready`/`degraded` by `_code()`.
Its docstring names the intended consumer, a "Desk/Workbench confidence strip," which does not
exist anywhere in the current UI — unlike the Name Manager case, nothing superseded this, the
UI half of it was simply never built. Both of its routes (`GET /api/readiness`,
`POST /api/readiness/probe`) exist and are pinned by `test_route_contract.py`, but nothing calls
the `POST` route, so `_LAST_PROBE` never populates and `GET` always returns "unknown."

**Decision: wire it up as part of batch 3, not as separate work.** Batch 3 already needs to
"extract the classifier so test-connection stops printing resolver exceptions" — `_code()` is
exactly that classifier, sitting unused. Reuse it there instead of writing a second one. Then
wire `probe()`/`snapshot()` into a real UI surface, most naturally replacing `/connections`'s
naive `bool(base_url) and token_is_set()` check (§3.2) with the real ready/degraded/unconfigured
status this module already computes.

---

## 10. Still unverified

- Learning-objective revision-protection holes: apply never verifies the target still matches
  `preview["outgoing"]`; the global `revision` counter causes cross-course false conflicts;
  `catalog_generation` churn. **[T]**
- `get_course_pages` asymmetries: current-course gated while modules and assignments are not;
  never age-gated; drops unpublished pages without reporting the count. **[T]**
- Module-to-page join via `content_id` vs `page_url` (same root as §4.1). **[T]**
- `source_refs` object shape undocumented against an exact-key validator. **[T]**
- Fields dropped at the pseudonym layer: `graded_at`, `cached_due_date`, `seconds_late`; and
  `late_policy_status` never stored at all. **[T]**
- `refresh_mirror`: 25s timeout against a sequentially paginated full pass, no progress
  signal, and expired-token errors collapsing into a generic "Sync failed." **[T]**
- `refresh_mirror` not refreshing groups, and `_roster_group_for_user` reading them with no
  freshness gate or label. **[T]**
- Course discovery dropping term, role, and concluded status (§3.7). **[T]**
- Standards versus learning objectives: `get_standards_profile` is per-student mastery, while
  the LO contract uses "TEKS-aligned" to mean a curriculum expectation, with no field to
  persist it. **[T]**
- First-run and navigation ("can the teacher find the page at all") has had no dedicated pass
  across these three scenarios.
- Nothing here was checked against a running app. Per this project's own history, rendered
  verification has caught real misses that green tests did not. Batches 2, 3, and 7 in §8 in
  particular should be verified in the browser, not only by test.
