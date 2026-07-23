# Author-and-stage — assistant-staged content overview

Status: design / planning (2026-07-21). Concept and slice map, not an execution brief.

## The idea

Any MCP-capable AI assistant, whichever one the teacher chooses to use, helps the teacher
create Canvas content and stages it for review and push. The assistant never writes to
Canvas and
never pushes anything. It reads what it needs through the MCP, writes a draft file into a
synced To Review folder, and the teacher reviews and pushes that draft through the review flow
Canvas Expert already has.

The loop:

1. The assistant reads the course's module structure and the authoring contract for the
   content type it is writing (new MCP reads).
2. The assistant authors a Forge envelope and drops it as a `.txt` file into a per-kind
   To Review folder in the workspace (a plain filesystem write, not an MCP call).
3. The file appears in the teacher's push tab. The teacher validates it and runs
   prepare -> review -> apply through the operation ledger, exactly as they do today for a
   file they authored themselves.

## What already exists (reuse, do not rebuild)

The audit that preceded this doc found most of the machinery is already here:

- **The review-then-push window is the operation ledger** (`api/operation_ledger/`):
  `prepare -> review -> apply` with drift detection (blocks on "a quiz with this title
  already exists"), a PII-minimized review summary, per-item New Quizzes finalization,
  crash-safe checkpointed steps, and a local-only mutation guard. It surfaces as the
  "Work -> Review -> Canvas" strip in `course_expert.html`.
- **Validators**: `/api/validate` (`api/validate_qf.py`) plus `/api/af/validate`,
  `/api/pf/validate`, `/api/rf/validate`. Four Forge envelopes: QuizForge,
  AssignmentForge, PageForge, RubricForge.
- **File discovery**: `api/webui/deps.py` `list_quiz_files` / `list_assignment_files` /
  `list_page_files` / `list_rubric_files` glob `*.txt` across the per-kind workspace
  folders defined in `api/runtime_paths.py::content_folders`. The push tabs already
  surface these files for validate-and-push.
- **Module storage**: the local course catalog (`api/course_catalog.py`, stored under
  `workspace.course_catalog_dir`) already holds `modules` with `{id, name, position,
  items:[{id, type, title, position, content_id}]}`. Readable with no Canvas call via
  `read_service.catalog_modules` and the `/api/course-catalog` route; `/api/modules`
  prefers local and falls back to live only when stale.
- **Contracts**: the Forge authoring contracts live in `LLM_Modules/*_Base.md`, with
  teacher/agent instructions in the Library/AI-TA folder.

So the push half, the validators, the review UI, and module storage are all built. The
gap is that an assistant cannot see modules or contracts through a supported channel, and
there is no clean place for it to drop a draft.

## The three parts

1. **See (new).** Two MCP read tools: `get_modules(course_id)` and
   `get_authoring_contract(kind)`.
2. **Stage (new, small).** Per-kind To Review drop folders in the workspace, globbed
   alongside the existing library; atomic write plus a done-marker.
3. **Push (exists).** The operation ledger review -> apply. No new code.
4. **Orient (docs).** START HERE / LEARN / the MCP instruction block so the assistant
   knows the loop exists and how to use it.

## Locked decisions

0. Vendor-neutral by design. The feature targets the MCP standard, not any one assistant,
   so a teacher can use whichever MCP-capable model they prefer. Add no model, provider,
   SDK, API key, or vendor-specific workflow. As CanvasMirror and Canvas Expert grow, the
   abilities available to every connected assistant grow with them.
1. The MCP never writes to Canvas and never writes content files. The new tools are reads
   only. The draft drop is the assistant's own filesystem write into the synced To Review, not
   an MCP tool. The push stays human-driven through the operation ledger. This preserves
   the existing safety posture whole: the assistant's only path to Canvas is to stage a
   file that a human then reviews and applies locally.
2. Read path is new MCP tools: `get_modules(course_id)` and `get_authoring_contract(kind)`.
3. Drop path is dedicated per-kind To Review folders in the workspace, globbed alongside the
   existing library so drafts show up in the push tabs while staying visually distinct from
   the teacher's own hand-authored files.
4. `get_modules` returns structural, non-PII data, so it needs no identity vault and no
   outbound safety gate. It is still scoped to active courses like the other tools, reads
   the local catalog only, and labels staleness rather than serving stale data silently.
   Modules are not refreshed on the sync heartbeat (only on demand or marked stale after an
   apply), so the tool reports freshness and leaves refresh to the teacher's existing
   on-demand catalog refresh, the same indirection principle as `refresh_mirror`.
5. `get_authoring_contract(kind)` serves the canonical Forge contract from one source
   (`LLM_Modules`), so the contract lives in exactly one place and the always-on
   instruction points to it rather than restating it.
6. Draft files carry no real Canvas identifiers. Anything student-specific stays in
   pseudonym space in the file; the teacher's push flow resolves real targets. This keeps
   the vault boundary intact even though the draft is a plain file on disk.
7. Drafts are written atomically with an explicit done-marker so Canvas Expert never picks
   up a half-synced OneDrive draft (the known workspace-churn hazard).

## Privacy and security boundary

- `get_modules`: structural data only, course-scoped, local-only, staleness visible. No
  student data, so no pseudonymization needed, but also nothing student-shaped ever flows
  through it.
- No new Canvas write path anywhere. Pushing remains the operation ledger behind the
  local-mutation guard (CSRF + loopback + same-origin).
- To Review drafts live in pseudonym space with no real IDs on disk.

## Slice map

Six core slices, each independently shippable, plus one optional cleanup. The push engine
needs no slice; it already exists.

- **Slice A — `get_modules` MCP tool.** Read modules from the local catalog
  (`read_service.catalog_modules`), course-gated, staleness labeled. Schema bump to v5;
  frozen v1-v4 kept. Smallest, fully independent, and directly answers the original "see
  modules via MCP" ask.
- **Slice B — `get_authoring_contract` MCP tool.** Serve the Forge contract for a kind from
  `LLM_Modules` so any assistant can author a valid envelope unattended. Independent of A.
- **Slice C — per-kind To Review drop folders.** Extend `content_folders` and the `deps.py`
  glob to include a workspace To Review per kind. Pickup ignores half-synced drops via the
  done-marker convention. This is the CE-side plumbing that makes a dropped file discoverable.
- **Slice D — To Review surfacing and validation in the push tabs.** Show assistant-staged
  drafts distinctly (badged pending review), run the existing validators on them, and show
  problems inline so a malformed draft is visible rather than silently failing. The
  teacher-facing half of staging.
- **Slice E — `list_staged_content` MCP read tool.** Let the assistant confirm its drop
  landed and see what is already pending, so it does not duplicate or lose track. Closes
  the loop.
- **Slice F — orientation docs.** MCP instruction block gains a short capability line
  pointing at `get_authoring_contract`; START HERE and LEARN_CANVASEXPERT gain the
  author-and-stage loop; the AI-TA authoring instructions are reframed from "paste into the
  web UI" to "author, then drop into To Review," vendor-neutral throughout.
- **Slice G (optional) — converge push preview onto the ledger planner.** Retire the legacy
  `qf_pusher` CLI dry-run path so the preview and the apply come from the same code. This is
  pre-existing tech debt the audit surfaced, not strictly part of author-and-stage, but it
  removes a reliability seam the staged flow would otherwise inherit.

## Open questions to settle before a build brief

- Exact To Review folder naming and whether the push tabs should badge assistant drafts
  distinctly from teacher files.
- Module staleness behavior for `get_modules`: return stale-with-label, or refuse and ask
  the teacher to refresh (mirror-consistent). Recommendation: stale-with-explicit-label for
  structural data, since the risk is far lower than for student data.
- Whether Slice A ships alone first as the immediate answer to the original request.

## Non-goals

- No MCP write to Canvas, and no MCP write-to-disk drop tool. The drop is a filesystem
  write the assistant already can do.
- No auto-push and no bypass of the operation-ledger review. The teacher always reviews
  and applies.
- No new Canvas identity, roster, or mirror route; `get_modules` reuses the existing local
  catalog.
