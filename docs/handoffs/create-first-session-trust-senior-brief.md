# Create first-session trust and staged-draft reality pass

**Status:** CURRENT direct execution brief  
**Executor:** one GPT-5.6 Luna implementation agent  
**Branch:** `dev`  
**Base:** current `origin/dev` after the executor's preflight fetch  
**Risk:** low-to-medium, local UI and read-only workspace staging only

This is the only execution authority in `docs/handoffs/`. Do not split the work,
add a planner/reviewer, or broaden it into a general UI cleanup.

## Teacher-visible objective

A teacher opening Create for the first time must know what is ready, what is
missing, and how to move from an ordinary AI chat to a reviewed Canvas Expert
draft without assuming Claude Desktop has already been installed or connected.

The complete slice is:

1. With no Current courses, Create gives the teacher an immediate, calm path to
   add one while explicitly allowing drafting and validation to continue.
2. The manual authoring path works with the AI chat the teacher already uses.
3. A finished assistant draft appears after the teacher returns to Create,
   distinguishes valid from invalid content, and enters the existing
   Validate -> Review flow.
4. A healthy empty inbox remains quiet; an actual inbox-load failure is visible
   and does not disable Library, Paste JSON, Upload, or any existing local
   validation path.

This slice stops before any Canvas write.

## Required context

Read only:

1. `AGENTS.md`.
2. `docs/reference/project-state.md`.
3. This brief.
4. `docs/reference/course-expert-module-map.md`:
   - `Ownership`
   - `Browser Routing`
   - `Guardrails`
5. `docs/reference/author-and-stage-overview.md`:
   - `The idea`
   - `What already exists (reuse, do not rebuild)`
   - `Locked decisions`
   - `Privacy and security boundary`
   - `Non-goals`
6. `docs/reference/webui-presentation-system.md`:
   - `Template API`
   - `Page conventions`
7. `api/webui/README.md`:
   - `Rendered verification (read-only)`
   - `Create (/course-expert)`

Do not read archived handoffs or the CanvasMirror information spine. Do not
change the Forge authoring contracts.

## Preflight — stop before writing if any assumption is false

1. Fetch `origin`, confirm the branch is `dev`, and compare local `dev` with
   `origin/dev` and local `main` with `origin/main`. Preserve unrelated worktree
   changes; stop if they overlap the allowed files below.
2. Confirm this is the only direct brief in `docs/handoffs/` besides
   `README.md`.
3. Confirm these seams still exist:
   - `course_expert.html` renders `.ce-forge-start`, `authoring_skills`, and four
     `[data-inbox-kind]` sections.
   - `push/inbox.js::initInboxSection` owns the initial, manual-refresh, and
     window-focus loads.
   - `file_sources.js` still exposes the `ceFileSource.setTempOption` and
     `setMode` seam used by staged drafts.
   - `GET /api/inbox-files` returns `{ok: true, files: []}` for a healthy empty
     kind and structured JSON for API failures.
4. Confirm a lifespan-disabled server boots from the repository root with:
   `py -m uvicorn api.webui.server:app --host 127.0.0.1 --port 8765 --lifespan off`.
   If the command documented in `api/webui/README.md` is still the non-working
   `cd api` form, correcting that command is in scope.
5. Do not modify the teacher's saved configuration to manufacture a course or
   workspace state. If the required zero-course or staged-file checks cannot be
   exercised through the real current state, an existing fixture, or a
   disposable isolated process, return YELLOW rather than editing private
   configuration.

## Locked product and technical decisions

### First-session course state

- When `saved_courses` is empty, render one prominent notice immediately inside
  the token-enabled Create stage and before `.ce-forge-start`.
- The notice says, in plain language, that there are no Current courses, links
  to `/settings#add-courses-card`, and explains that the teacher may still draft
  and validate now but must add a course before sending to Canvas.
- Keep the authoring panel and all Create tabs available. Do not replace the page
  with a setup wall.
- Do not show this notice when one or more Current courses exist.
- Keep the existing empty message inside the course picker as local context; do
  not create a second setup flow.

### Assistant wording

- Keep the heading `Start in your assistant`.
- Describe the primary path as using the AI chat the teacher already uses:
  copy or download the canonical instruction file, ask for the content, then
  Paste JSON or Upload the returned file.
- Provider examples may appear only as secondary examples. Do not make any
  provider a prerequisite or add provider-specific behavior.
- A teacher who has never opened Claude Desktop must be able to complete the
  manual path without visiting AI Connections.
- An optional AI Connections link may explain connected course context. Do not
  imply that MCP itself writes draft files: automatic staging is available only
  when the connected assistant also has access to the workspace.

### Staged-draft state model

For each of the four existing inbox sections:

- **Loading:** do not flash an error or empty panel.
- **Healthy empty:** keep the section hidden.
- **Ready:** show every returned draft, preserving the existing Valid / Needs
  fixes presentation, inline validator problems, and `Use this draft` action.
- **Degraded:** show a compact, actionable message such as “Staged drafts
  couldn’t be checked. Paste or upload still works.” Keep Refresh available.
- Treat a non-2xx response, invalid JSON, `ok: false`, or thrown fetch as
  degraded. Do not silently reinterpret it as an empty inbox.
- A later successful load must recover from degraded to either healthy-empty or
  ready without reloading the page.
- Preserve escaping of every server-provided label, path, and problem.
- Preserve the existing `ceFileSource` handoff; do not build a parallel file
  selection or validation path.
- Keep the current initial load, explicit Refresh, and window-focus recheck.
  Add no polling, timer loop, persistence, registry, or service worker.
- Prevent an older request from overwriting a newer result if loads overlap.
  The smallest request-generation or equivalent latest-result guard is enough.

### Presentation boundary

- The browser title for `/course-expert` must be `Create — Canvas Expert`, matching
  the nav label and visible page title.
- Use existing notice, panel, button, spacing, and color tokens. Add no new
  palette, shadow, radius, or typography system.
- Do not change any other page title, layout shell, rail, heading scale, or
  navigation label in this batch.

## Allowed implementation scope

Primary files:

- `api/webui/templates/course_expert.html`
  - browser title;
  - zero-course notice immediately before `.ce-forge-start`;
  - provider-neutral manual authoring wording.
- `api/webui/static/push/inbox.js`
  - explicit loading / empty / ready / degraded behavior;
  - latest-result protection;
  - recovery through Refresh and focus.
- `api/webui/static/pages/course_expert.css`
  - only the minimal Create-owned styling needed for the new notice or degraded
    inbox state.

Conditional files:

- `api/webui/static/course_expert/tabs.js` only if the existing copy/link wiring
  cannot support the locked wording without a behavior change.
- `api/tests/test_presentation_contracts.py` for route-render assertions covering
  the Create browser title and zero-course notice.
- Existing focused inbox tests under `api/tests/test_inbox_files*.py` only if a
  backend contract regression is discovered. The backend response shape is not
  expected to change.
- `api/webui/README.md` only to correct the verified lifespan-disabled startup
  command or keep its Create description accurate.

Do not modify settings behavior merely because the notice links to Settings.

## Acceptance criteria

All criteria are independently required:

1. A token-enabled render with zero Current courses contains exactly one
   first-session course notice before the assistant panel, links to
   `/settings#add-courses-card`, and keeps the authoring panel and tabs present.
2. The same render with at least one fictional Current course does not contain
   that notice.
3. The browser title, primary nav label, and visible page title all say `Create`.
4. Copy and Download still use the canonical files from
   `api/default_docs/AI Authoring/`; no contract text is copied into the template
   or JavaScript.
5. A teacher can understand and complete the manual authoring path without
   Claude Desktop, an MCP connection, or an AI API key.
6. A healthy `{ok: true, files: []}` response leaves the matching staged section
   hidden and produces no warning.
7. A valid staged draft becomes visible after initial load, Refresh, or a return
   of window focus; `Use this draft` selects it through the existing file-source
   seam.
8. An invalid staged draft remains visible, shows its validator problems, and
   offers no `Use this draft` action.
9. A non-2xx response, `ok: false`, invalid JSON, or network failure produces the
   compact degraded state while Library, Paste JSON, Upload, and existing
   validation controls remain usable.
10. A later successful response clears the degraded state without a page reload,
    and an older overlapping request cannot replace the newer result.
11. No check starts a Canvas write, routine, external AI request, session, or
    operation-ledger apply.
12. No secret, course name, student data, private path, or temporary staged
    content enters the repository or test output.

## Named verification gate

Run:

```powershell
py -m pytest api/tests/test_presentation_contracts.py api/tests/test_inbox_files.py api/tests/test_inbox_files_route.py api/tests/test_route_contract.py -q
```

Do not run the full API or engine suite unless a focused failure demonstrates
unexpected coupling.

Then perform rendered verification with the lifespan-disabled server:

```powershell
py -m uvicorn api.webui.server:app --host 127.0.0.1 --port 8765 --lifespan off
```

Verify `/course-expert` at:

- 1440 x 900 in light and dark themes;
- 760 x 900 in one theme.

For the rendered pass:

- confirm `document.documentElement.scrollWidth === window.innerWidth`;
- confirm one app header and one `ce-page-header`;
- confirm the zero-course notice is visible in the real current empty state or a
  disposable isolated equivalent;
- confirm Copy reports success and Download still targets the canonical file;
- exercise healthy-empty, valid, invalid, degraded, and recovery states;
- confirm a newly completed fictional draft appears after leaving and returning
  focus without reloading;
- confirm `Use this draft` hands off to the existing file source;
- confirm zero new CanvasExpert console errors or warnings;
- inspect network activity and confirm no Canvas write, AI request, routine,
  session start, or operation apply occurs.

The staged-file check may create only one uniquely named, fictional,
student-free draft and its exact `.done` marker in the private To Review
workspace. Record the two exact paths before creation, remove only those two
files after verification, and report cleanup. Never use a glob or recursive
delete.

## Explicit non-goals

- No Canvas push, dry run, operation preparation, or ledger change.
- No Forge parser, validator, authoring-contract, or content-format change.
- No Settings rail or section reordering.
- No Automations/document-shell work.
- No Student reports layout or routing work.
- No PowerGrader naming or session-label consolidation.
- No mirror, session-store, connection-client, MCP-tool, or workspace-format
  change.
- No new onboarding wizard, assistant integration, polling system, test harness,
  registry, persistence, or migration behavior.
- No attempt to repair unrelated stale reference documents in this batch.

## Stop conditions

Return RED before implementation if:

- Create no longer uses the named inbox/file-source seams;
- satisfying the slice requires a Forge contract, Canvas write path, Settings
  behavior, MCP contract, or workspace format change;
- the only way to render the required states is to alter the teacher's saved
  configuration or expose private data;
- another subsystem or public contract must change.

Return YELLOW if:

- implementation is bounded and complete but one required rendered state cannot
  be exercised safely;
- the named focused gate cannot run for an environmental reason;
- one product decision remains that materially changes the teacher path.

## Execution result

**YELLOW — rendered shell verification passed, but required staged-draft interaction
states remain unverified.**

- **Commit / push:** none; changes are unstaged for senior review.
- **Changed files:** `api/webui/templates/course_expert.html`,
  `api/webui/static/push/inbox.js`, `api/webui/static/pages/course_expert.css`,
  `api/tests/test_presentation_contracts.py`, and this execution result.
- **Named gate:** `py -m pytest api/tests/test_presentation_contracts.py api/tests/test_inbox_files.py api/tests/test_inbox_files_route.py api/tests/test_route_contract.py -q`
  — **30 passed**, 0 failed (1.52s).
- **Server preflight:** `py -m uvicorn api.webui.server:app --host 127.0.0.1 --port 8765 --lifespan off`
  started successfully from the repository root; `GET /course-expert` returned 200.
- **Rendered matrix:** `/course-expert` rendered at 1440x900 in light and dark
  themes and at 760x900 in dark theme. Each view had exactly one app header and
  one `ce-page-header`, no horizontal overflow, zero console warnings/errors, and
  the zero-course notice visible. A valid staged Page draft was visible in the
  browser, and `Use this draft` selected it through the existing file-source
  combobox. After exact cleanup, the Page inbox root was hidden with
  `state=empty`, had no degraded message, and desktop `scrollWidth` was 1425 at
  a 1440px viewport. Copy was initiated, but completion feedback and clipboard
  contents were not observable in the browser.
- **Local staged-file lifecycle:** with the pre-existing private To Review Pages
  inbox empty, one uniquely named fictional PageForge draft and its matching
  byte-length `.done` marker were created there. `GET /api/inbox-files?kind=page`
  returned: healthy empty (0 files); valid (1 file, valid, 0 problems); invalid
  (1 file, invalid, problems present); and valid recovery (1 file, valid,
  0 problems). The exact two files were then removed and the endpoint again
  returned healthy empty (0 files). Exact private paths were recorded before
  creation and used for cleanup, but are not copied into this repository under
  the no-private-path guardrail.
- **Browser interactions still unverified:** invalid/degraded presentation and
  recovery, focus refresh, Copy completion, Download, and
  browser network inspection. The valid-draft presentation and `Use this draft`
  handoff are verified; the local route evidence above is not presented as a
  substitute for the remaining browser proof.
- **Temporary browser-check files:** one uniquely named fictional valid PageForge
  draft and matching byte-length `.done` marker were created only in the existing
  private To Review Pages folder for the browser handoff check. Both exact files
  were removed afterward; `GET /api/inbox-files?kind=page` returned `ok: true`
  with 0 files, and exact-path existence checks were false. Private paths are not
  copied into the repository under the no-private-path guardrail.
- **Deviations:** none in implementation. The brief's historical "Terra executor"
  wording was not otherwise changed; execution used Luna as specified in its header.
- **Unresolved decision:** provide an approved browser interaction surface with
  safe local state control for the remaining presentation, focus, handoff, and
  network checks before this can be accepted GREEN.
