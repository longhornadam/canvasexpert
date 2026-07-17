# CanvasMirror v3 — one source of reads, complete feedback data, safe on two machines

Status: orchestration plan — not yet started
Risk: medium (read-path migration; no write-path changes anywhere)
Owner/orchestrator: Claude (strong model, main session)
Executors: one subagent per slice (weaker models acceptable — every slice spec
below is self-contained and assumes no context beyond this document)

---

## Run state ledger (orchestrator-maintained — single source of truth)

The orchestrator MUST update this table and the session log immediately after
each slice transition, in the same edit as the slice's commit. Any session —
including a fresh one after a usage wall — resumes from this table alone.

| Slice | Title | Status | Commit |
|---|---|---|---|
| 1 | Work-discovery providers read the mirror | in_progress (unblocked by slice 5; re-dispatched) | — |
| 2 | Routine sweeps read the mirror (display reads only) | pending | — |
| 3 | Curve listing reads the mirror (preview/apply stays live) | pending | — |
| 4 | PowerGrader session creation: delta-then-disk | pending | — |
| 5 | Submission comments in the mirror | done | f403a29 |
| 6 | Vault multi-machine hardening | done | c31543b |

Statuses: `pending` → `in_progress` → `done` | `blocked: <one-line reason>`

### Session log (append-only)

- 2026-07-16: Plan authored. No execution yet.
- 2026-07-16: Execution started. Slices 1, 5, 6 dispatched in parallel
  (non-overlapping files); 2–4 queued behind 1.
- 2026-07-16: Slice 1 agent correctly blocked per guardrail: grading_debt
  (_teacher_touched, ~42) and home_attention (_ordered_comments, ~51) read
  submission_comments from the submissions path; field lands in slice 5.
  Re-sequenced 5 → 1. Accepted tradeoff to record on slice 1 completion:
  comment-dependent providers tolerate ≤24h comment staleness (full-pass
  capture only), self-correcting nightly. late_work + roster_warnings fields
  verified clean against mirror shapes.
- 2026-07-16: Slice 5 done (f403a29). Orchestrator-verified: 83 targeted
  tests green; diff matches spec (additive normalizer, full-pass-only
  include, preserve-on-merge both paths). Known limitation recorded: a
  comment deleted in Canvas persists at rest — an empty list is
  indistinguishable from a lean fetch; benign for attention-card consumers.
  Slice 1 unblocked and re-dispatched (mirror rows now carry
  submission_comments).
- 2026-07-16: Slice 6 done (c31543b). Orchestrator-verified: 112 targeted
  tests green; fail-closed check sits before any student data in all three
  MCP tools; vault assignment logic untouched. NQ v2 post-review hardening
  committed separately (470272c). Slice 1 retry still in flight.

---

## Resume protocol (for any future session)

1. Read this document top to bottom. Read `docs/mirror.md` (design laws).
2. Run `python -m pytest api/tests/ -q` from repo root. Baseline at plan time:
   **831 passed, 1 skipped**. If the suite is red, fix or revert to the last
   ledger commit before proceeding.
3. Check `git status`. Uncommitted work + a slice marked `in_progress` means a
   session died mid-slice: inspect the diff against that slice's spec; finish
   or `git checkout -- .` and restart the slice. The specs are written so a
   restarted slice is safe.
4. Continue at the first slice not marked `done`. Slices 1–4 are sequential
   (they share seams). Slices 5 and 6 are independent of 1–4 and of each
   other — they may run in parallel with anything.
5. After each slice: run its verification block, run the full suite, commit
   (policy below), update the ledger + session log.

**Commit policy (persistence mechanism):** one commit per completed slice,
message `feat(mirror-v3): slice N — <title>`, ending with the standard
Claude co-author line. This is what makes a usage wall harmless — never let
two slices sit uncommitted.

---

## Objective

Close CanvasMirror's three structural gaps:

1. **One source of reads.** A dozen read sites still fetch live Canvas while
   the mirror heartbeat fetches the same data on an overlapping timer —
   double load, two freshness stories. After v3, background/display reads go
   through the mirror; live Canvas remains only for writes, write-preflights,
   and explicit fallbacks.
2. **Complete feedback data.** Submission comments — where teacher-student
   feedback dialogue lives — enter the mirror, completing the
   attempt → feedback → attempt substrate.
3. **Safe on two machines.** `vault.json` (the one irreplaceable secret)
   gets cross-machine conflict detection before a second install exists.

### Non-goals (do not do these in v3)

- No views layer (regrade queue, revision chains) — that is v4, after reads
  converge.
- No write-path changes of any kind. No changes to `new_quiz_grader.py`,
  `qf_pusher.py`, `session_actions.py` write functions, or the operation
  ledger's execute/verify paths.
- No MCP tool additions or schema changes (`tool_schema_v*.json` untouched).
- No changes to `feedback_safety.py`, `feedback_scrub.py`, or `Vault`
  pseudonym-assignment semantics (slice 6 adds integrity checks around the
  vault file; it does not change how pseudonyms are assigned or scrubbed).
- No new store schema versions. Slice 5 extends v1 submission files with one
  additive key; everything else reads what exists.

---

## Locked decisions

1. **Reads that feed a write decision stay live.** Curve preview/apply
   baselines, operation-ledger drift/baseline reads, and any read whose
   result is transformed into a Canvas write must fetch live Canvas. A stale
   mirror row must never influence a grade that gets written. When in doubt:
   if the data flows toward `_canvas_send`, it is live.
2. **Mirror-first is fallback-safe and labeled.** Every flipped read serves
   from the mirror only when fresh (`api/mirror/queries.py` freshness
   helpers, config `mirror_serve_max_age_hours`), falls back to the existing
   live call otherwise, and — where the payload reaches a UI or MCP surface —
   carries `source` + `synced_at`. Internal aggregations may skip labeling.
3. **Store schema is orchestrator-owned.** If a flipped consumer needs a
   field the mirror doesn't store, the subagent does NOT widen normalizers.
   Mark the slice `blocked:` with the field name; the orchestrator decides.
4. **Test seams keep working.** Existing tests monkeypatch live fetchers.
   Every flip must preserve the pattern already used in
   `api/mcp_server/tools.py` / `api/gradebook_snapshot.py`: explicit
   overrides and patched seams bypass the mirror entirely.
5. **PowerGrader grades current work.** Session creation may read submission
   bodies from disk only immediately after a successful synchronous delta for
   that course ("delta-then-disk"). If the delta fails, fall back to the
   existing live fetch. Never grade from an un-refreshed mirror.

---

## Global contract (include verbatim in every subagent dispatch)

**Repo:** `D:\Development Projects\CanvasExpert`. Python FastAPI app. Run
tests with `python -m pytest <files> -q` from repo root.

**The mirror API you consume (do not modify except where a slice says so):**

- `api/mirror/store.py` — collections under
  `_System/Canvas Mirror/<course_id>/`: `read_roster(course_id, *, root=None)`,
  `read_assignments(...)`, `read_submissions(course_id, assignment_id, *, root=None)`,
  `read_sync(...)`. Writers: `write_roster`, `write_assignments`,
  `merge_submissions(..., replace=bool)`, `record_pass`. All paths resolve at
  call time; every function takes `root=` for tmp_path tests.
- `api/mirror/queries.py` — `gradebook_queries`-shaped reads, each returning
  `(data, error)`: `course_students`, `course_assignments`,
  `course_submissions`, `assignment`, `assignment_submissions`. Freshness:
  `data_freshness(course_id) -> synced_at | ""`,
  `roster_freshness(course_id) -> synced_at | ""` (empty string = do not
  serve; fall back live).
- `api/mirror/sync.py` — `full_pass` / `delta_pass` / `roster_pass`, each
  `(course_id, *, canvas_get_all, root=None, now=None) -> {"ok": bool, ...}`.
- `api/webui/mirror_service.py` — heartbeat + `notify_course_changed`.

**Row shapes:** mirror rows are Canvas-shaped dicts with **string** ids
(`user_id`, `assignment_id`, `id`). Live Canvas returns ints. Flipped code
must tolerate both (compare with `str(...)` on both sides).

**Test conventions:** no conftest fixtures exist. Redirect the workspace with
`monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))`
(`from api.webui import workspace`). Populate the mirror with `store.write_*`
+ `store.record_pass(course_id, "full", ok=True)` using a fresh
`store.now_iso()` timestamp for "fresh" cases and a pinned old ISO string for
"stale" cases. Copy the fixture style of `api/tests/test_mirror_queries.py`.
Synthetic data only: fake names like "Learner One", ids like 900001/700010.

**Forbidden:** anything in the Non-goals list; new dependencies; changes to
`api/mirror/store.py` normalizers; edits to `docs/` other than what your
slice specifies; committing (the orchestrator commits).

**Definition of done for every slice:** new/updated tests pass; the FULL
suite passes (`python -m pytest api/tests/ -q`); `git diff` contains only
files your slice names; a 5-line summary of what changed and why, returned
as your final message.

---

## Slice 1 — Work-discovery providers read the mirror

**Problem.** The work-registry providers fetch assignments/submissions/users
live on the routines heartbeat: `api/work_registry/providers/late_work.py`
(~32–39), `grading_debt.py` (~57–64), `home_attention.py` (~104–111),
`roster_warnings.py` (~45–171). All go through the shared wrapper
`call_canvas_get_all` in `api/work_registry/providers/__init__.py` (~83).

**Approach — flip at the wrapper, not per provider.** In
`providers/__init__.py`, add a mirror shim in front of `call_canvas_get_all`:
when the requested path matches one of exactly three shapes for a course —
`/api/v1/courses/{id}/assignments`, `/api/v1/courses/{id}/users`,
`/api/v1/courses/{id}/students/submissions` — and
`mirror_queries.data_freshness(course_id)` (or `roster_freshness` for users)
is non-empty, serve `(rows, None)` from the corresponding
`api/mirror/queries.py` function instead of calling Canvas. Any other path,
any staleness, any mirror error → existing live call, unchanged. Recognize
paths with one compiled regex per shape; extract `course_id` from the path.

**Guardrails.** First Read each provider and list which row fields it
consumes; verify each against the mirror row shapes in
`api/mirror/store.py` normalizers (`normalize_student`, `normalize_assignment`,
`normalize_submission`). If any consumed field is absent from the mirror
shape, STOP and report `blocked: provider <name> needs field <field>` —
do not widen anything. Note the int/str id rule from the global contract.

**Tests** (new file `api/tests/test_work_providers_mirror.py`): fresh mirror
→ providers produce work items with zero live calls (monkeypatch the live
`_canvas_get_all` to raise); stale mirror → live fallback used; non-matching
path always live; str-id rows aggregate correctly.

**Verify:** `python -m pytest api/tests/test_work_providers_mirror.py api/tests/test_work_discovery.py api/tests/test_work_routes.py -q` then full suite.

---

## Slice 2 — Routine sweeps read the mirror (display reads only)

**Problem.** `api/webui/routes/routines_builtin.py` (~35–54, 111, 146,
189–218, 252–258) and `api/webui/gradebook_service.py::_sweep_compute`
(~289–349) fetch live per routine tick.

**Approach.** Same shim idea, applied locally: where these functions fetch
the three course-scoped datasets, try the mirror queries first (freshness-
gated), fall back live. Factor ONE helper (suggested:
`api/webui/mirror_reads.py`, ~40 lines) exposing
`students_or_live(course_id)`, `assignments_or_live(course_id)`,
`submissions_or_live(course_id)`, each returning `(rows, error, source)` —
and use it in both files. Slice 1's wrapper may be refactored onto this
helper if trivially compatible; otherwise leave slice 1 as is and note it.

**Critical exclusion (locked decision 1):**
`api/operation_ledger/adapters/sweep.py` (~291–302) also fetches these
datasets, but as an execute/baseline path for writes — DO NOT TOUCH IT.
`_sweep_compute` itself is used for preview/display; if you find its output
flowing directly into a `_canvas_send` without a fresh live re-read, STOP and
report `blocked:` with the call chain instead of flipping it.

**Tests** (new `api/tests/test_mirror_reads_helper.py` + additions to
existing sweep/routines tests): helper serves fresh-mirror rows without live
calls; stale → live; `_sweep_compute` output identical for equivalent
mirror/live data (same fixture both ways).

**Verify:** targeted tests + full suite.

---

## Slice 3 — Curve listing reads the mirror; preview/apply stays live

**Scope (small).** In `api/webui/routes/gradebook_curves.py`:
`curve_assignments` (~17) lists assignments for the picker — flip it to the
slice-2 helper (mirror-first, live fallback). `curve_preview`, `curve_apply`,
`revert_curve`, and everything in `api/operation_ledger/adapters/curve.py`
read score baselines that feed grade writes — **leave every one of them
live** (locked decision 1). Add a one-line comment at the top of the route
file stating that boundary so a future edit doesn't "helpfully" flip them.

**Tests:** extend `api/tests/test_gradebook_routes.py` (or the curves test
file if separate): fresh mirror serves the assignment list with zero live
calls; preview/apply still call live fetchers (monkeypatch mirror to raise
if consulted by those routes).

**Verify:** targeted tests + full suite.

---

## Slice 4 — PowerGrader session creation: delta-then-disk

**Problem.** `api/powergrader/canvas_fetch.py` (~34) live-fetches all
submissions when building a grading session — the slowest teacher-facing
wait in the app.

**Approach (locked decision 5).** Before assembling submissions for a new
session: call `mirror_service.sync_now(course_id)` synchronously (it runs a
delta; a never-synced course automatically gets a full pass — acceptable,
message the estimate). If the returned summary has `ok: True`, read
submissions via `api/mirror/queries.assignment_submissions(course_id,
assignment_id)` and proceed from disk — bodies, attempts, flags all present.
If the delta fails OR the mirror read errors, fall back to the existing
live fetch, unchanged. New Quiz flow (v2 `cached_snapshot` path) is separate
and untouched. Result: session creation costs ~3 Canvas requests
(delta) instead of a full paginated submission pull, and repeat sessions on
the same course within minutes cost zero.

**Guardrail:** the delta is mandatory — never serve session bodies from an
un-refreshed mirror, even if `data_freshness` says fresh. Grading is a write
precursor; 15 minutes is too stale (a student may have resubmitted).

**Tests** (extend `api/tests/test_powergrader_attachment_workflow.py`
fixtures or new `test_powergrader_mirror_session.py`): successful delta →
session built from mirror rows, live submission fetch not called; failed
delta → live fallback; resubmission arriving in the delta appears in the
session.

**Verify:** targeted + full suite. Also run
`api/tests/test_powergrader_new_quizzes.py` explicitly (adjacent code).

---

## Slice 5 — Submission comments in the mirror (independent; parallel-safe)

**Approach.** Additive, full-pass-only:

1. `api/mirror/sync.py::full_pass`: add `"submission_comments"` to the
   `include[]` list of its `_fetch_submissions` call (full pass only — the
   delta stays lean; comment staleness is bounded by the nightly full pass,
   document that in `docs/mirror.md`'s blind-spot bullet).
2. `api/mirror/store.py::normalize_submission`: add one key to `current`:
   `"submission_comments"`: list of
   `{"author_id": str, "comment": str, "created_at": str}` — exactly those
   three fields, from `row.get("submission_comments") or []`. No author
   names, no avatars, no attachments (author identity resolves through the
   roster/vault when a consumer needs it). This is the ONE permitted
   normalizer change in v3; update `_SUBMISSION_FIELDS`-adjacent validation
   only if the exact-key check requires it (it validates entry shape, not
   current's keys — confirm by reading `validate_submissions`).
3. MCP stays unchanged this slice — `pseudonymize_submission_rows` does not
   emit comments, so nothing new can leak. (Exposing comments through MCP is
   v4 work with its own scrub design.)

**Tests** (extend `api/tests/test_mirror_store.py` +
`test_mirror_sync.py`): comments round-trip through full pass; delta merge
of a row WITHOUT comments does not erase stored comments — if it does,
preserve-on-merge logic is required in `merge_submissions` (carry
`submission_comments` from the previous entry when the incoming row lacks
the key); MCP `get_submissions` output still contains no comment text
(assert on the dumped payload).

**Verify:** targeted + full suite + `api/tests/test_mcp_server_tools.py`.

---

## Slice 6 — Vault multi-machine hardening (independent; parallel-safe)

**Problem.** `api/feedback_vault.py` (`vault.json` in
`_System/Identity Vault/`) is the only irreplaceable artifact. Two machines
+ OneDrive can produce a conflict fork: same student, two pseudonyms.

**Approach — detect and refuse-to-diverge; do NOT redesign assignment:**

1. **Machine stamping.** On every vault save, write
   `{"written_by": <machine_id>, "written_at": <iso>, "entry_count": N}`
   into the document root (reuse `machine_id` from
   `api/powergrader/autoscore_claims.py`). Loader tolerates the keys'
   absence (legacy vaults).
2. **Conflict-copy detection.** On `Vault._load()`, glob the vault directory
   for OneDrive conflict artifacts (`vault*.json` beyond the canonical name —
   OneDrive names them like `vault-<ComputerName>.json` or
   `vault (1).json`). If found: do NOT guess-merge. Set a module-level flag
   exposed as `vault_conflict() -> list[str]`.
3. **Surface, don't block silently.** `api/webui/routes/names.py` (the vault
   UI) and `GET /api/mirror/status` gain a `vault_conflict` warning field.
   The MCP student-data tools, when `vault_conflict()` is non-empty, return
   `{"ok": False, "error": "identity vault conflict detected — resolve in
   the CanvasExpert web UI before pseudonymized reads continue"}` — fail
   closed, because a forked vault can assign a second pseudonym to the same
   student and silently break scrub coverage.
4. Deliberately manual resolution in v1 of this: the UI warning tells the
   teacher which files exist and to keep the newest complete one. No
   auto-merge code.

**Tests** (new `api/tests/test_vault_conflict.py`): stamped save
round-trips; legacy vault loads; planted `vault-OTHERPC.json` → conflict
reported, MCP `get_roster` fails closed with no student data in the error;
no conflict → everything normal.

**Verify:** targeted + full suite + `api/tests/test_mcp_server_tools.py`
+ `api/tests/test_beta075_mcp.py`.

---

## Orchestration protocol

1. **Dispatch:** one Agent per slice. Prompt = the Global contract block +
   that slice's section, verbatim, plus: "Work only in the listed files.
   Return the 5-line summary. Do not commit."
2. **Order:** 1 → 2 → 3 → 4 sequentially. 5 and 6 may run in parallel with
   anything (different files). Never two agents on overlapping files.
3. **Review gate (orchestrator, per slice):** read the diff hunk-by-hunk
   against the slice spec; check the locked decisions (especially: no write
   path touched, seams preserved, no normalizer changes outside slice 5);
   run the slice's verification block + full suite yourself — do not trust
   the agent's claim.
4. **On pass:** commit (policy above), update ledger + session log.
5. **On fail/blocked:** either fix inline (small) or revert the working tree
   and mark `blocked:` with the reason. A blocked slice never leaves partial
   code uncommitted past the session.
6. **Usage-wall discipline:** the ledger edit + commit happen together,
   immediately, before starting the next slice — never batched. If an agent
   dies mid-slice, the working tree is the only loss; resume protocol
   handles it.
