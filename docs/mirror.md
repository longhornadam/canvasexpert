# CanvasMirror

This file documents current implemented behavior. The 1.0-beta target architecture and
migration program live in
`docs/reference/canvasmirror-1.0beta-information-spine.md`; that vision does not supersede
the current contracts until its individual implementation briefs are completed.

A disposable local mirror of Canvas course facts, kept fresh by deterministic
background sync, living in the synced workspace at `_System/Canvas Mirror/`.
Reads that used to cost live Canvas round trips (gradebook snapshot, MCP
roster/submissions) are served from disk in milliseconds when the mirror is
fresh — and fall back to live Canvas, visibly labeled, when it isn't.

## Design laws

1. **Canvas is truth; the mirror is disposable.** Every file under
   `Canvas Mirror/` can be deleted and rebuilt by re-sync. Corrupt or invalid
   files are treated as absent, never repaired in place.
2. **Sync is deterministic.** No LLM anywhere in the data path. CanvasExpert's
   heartbeat moves data; assistants only consume the result.
3. **Real data at rest under teacher custody** — the same boundary as Canvas
   itself. Pseudonymization stays exactly where it was: at the outbound
   MCP/LLM gate. The mirror changes where reads come from, never what leaves
   the machine.
4. **Freshness is always visible.** Every collection carries an envelope
   (`state`, `last_success_at`, `last_attempt_at`, `error_code`); every
   mirror-served read is labeled `source: "mirror"` + `synced_at`; live
   fallbacks are labeled `source: "canvas"`. Staleness is never silent.
5. **Foreground wins.** Sync runs on a background heartbeat and yields to
   whatever the teacher is doing.

## On-disk layout

```
<workspace>/_System/Canvas Mirror/<course_id>/
  _sync.v1.json                    pass envelopes + delta watermarks
  roster.v1.json                   students + sections (consumer fields only —
                                   no emails, no avatars)
  assignments.v1.json              slim Canvas-shaped assignment index
                                   (the authoring catalog stays the rich source)
  submissions/<assignment_id>.v1.json
                                   per-student current row + append-only attempts
  new_quiz_capability.v1.json      New Quiz metadata-scope capability record
                                   (student-free; see "New Quiz capability gate" below)
  new_quizzes/_sync.v2.json        New Quiz metadata/response freshness envelopes
  new_quizzes/<assignment_id>/quiz.v2.json
                                   assignment, quiz, and item catalog metadata
  new_quizzes/<assignment_id>/students/<user_id>.v2.json
                                   on-demand report attempts and URL-free evidence
```

Per-assignment submission files keep OneDrive syncs small and localize any
cross-machine conflict to a single disposable file.

## Sync passes (`api/mirror/sync.py`)

- **full** — backfill and nightly reconcile are the *same code path*: fetch
  everything (with `submission_history`), rewrite collections with
  attempt-preserving replace merges, prune assignments/students that no
  longer exist, reset watermarks. The full pass is also the only thing that
  can fix `missing`-flag drift: Canvas flips `missing` when a due date passes
  with no student action, which no delta can ever observe.
- **delta** — two course-level questions since the last watermark:
  `submitted_since` (with history — catches resubmissions as new attempts)
  and `graded_since`. Near-empty for stagnant courses; a stagnant assignment
  costs zero requests forever.
- **roster** — students + sections; rosters rarely change, so daily.

Watermarks advance only on success, to pass-start minus a 10-minute overlap;
store merges are idempotent so overlap duplicates are harmless. Failures
degrade the pass envelope (`stale` after a prior success, `unavailable`
before one) and never touch collection files.

**Attempt history is append-only** within a living submission: students who
resubmit accumulate `attempts` keyed by attempt number, which survive full-
pass rewrites. This is the substrate for regrade queues, revision chains, and
growth-over-time views. (Deleted submissions take their attempts with them —
the mirror mirrors truth.) New Quiz response snapshots follow the same law:
attempts captured earlier but absent from a later report are carried forward,
while `current`/`latest_attempt` always reflect the newest fetch alone.

## Scheduling (`api/webui/mirror_service.py`)

A daemon heartbeat (started in the server lifespan, alongside the routines
heartbeat) ticks every 15 minutes for Current courses only:

- first tick 2 minutes after launch (catch-up)
- **full** when none has succeeded in 24 h (first-run backfill, then nightly)
- otherwise **delta** every tick, plus **roster** daily
- `notify_course_changed(course_id)` — write-through hook: after CanvasExpert
  itself pushes grades (PowerGrader push, curve apply/revert), a short-delay
  delta teaches the mirror its own actions without waiting for the next tick.

Config (machine-local): `mirror_enabled` (default true),
`mirror_serve_max_age_hours` (default 6 — older than this, readers fall back
to live Canvas).

Routes: `GET /api/mirror/status` (per-course pass envelopes + watermarks),
`POST /api/mirror/sync-now` (manual delta; falls back to a full backfill for
a never-synced course — the first one can take a minute).

New Quiz metadata follows the same full/delta cadence without generating
Student Analysis reports. Per-quiz metadata fetches are skipped while the
stored doc is current (unchanged assignment `updated_at`, under a 24 h
true-up age) — a stagnant quiz costs zero requests per tick; the daily
true-up bounds staleness from item edits that don't bump `updated_at`. PowerGrader's focused New Quiz acquisition writes
the response snapshot on success. A fresh response snapshot can satisfy a
later PowerGrader read without another ordinary submission/report read; native
file evidence still uses the focused live transport.

### New Quiz capability gate (1.0beta slice 01a)

New Quiz endpoints are gated on active enrollment (`api/README.md` ~205-213): the
same token returns 200 in an actively-enrolled course and 403 in a
concluded/past-enrollment course, deterministically, for every quiz. Design:
**lifecycle predicts, probe confirms, circuit backstops**
(`docs/reference/canvasmirror-1.0beta-information-spine.md` Sec 9.4) — this
slice implements the probe/circuit half only; no lifecycle signal exists yet.

`sync_metadata` (`api/mirror/new_quizzes.py`) keeps a small, student-free
capability record per course (`new_quiz_capability.v1.json`, via
`api/mirror/store.py`'s course_dir/course_lock/atomic-write conventions —
its own file rather than widening `_sync.v1.json`'s schema): `capability`
(`supported` / `restricted` / `unknown`), `last_probe_at`, `retry_after`, and
a sanitized `evidence` (`forbidden` / `unauthorized` category + consecutive
failure count). No status text, response bodies, URLs, or quiz titles are
stored.

Classification: 3 consecutive distinct-quiz `HTTP 403`/`HTTP 401` failures
(parsed from the existing canvas_client error-string prefix) with zero
successes in one `sync_metadata` run opens the circuit — `restricted`,
`retry_after` = now + 24h. Any single success in a run clears it. A mixed run
(some 200, some 403) stays `supported` — those failures are item-level noise.

Gate: while restricted and the cooldown has not expired, `sync_metadata`
skips the entire fan-out (zero Canvas calls) and records the run as
skipped-restricted. Once the cooldown passes, the next run makes one bounded
probe (the first quiz only) — a 403/401 renews the cooldown without touching
the rest; a success clears the restriction and the remaining quizzes are
processed normally in the same run. A transient probe failure (timeout, 5xx,
connection, invalid response) never renews the cooldown — the record stays
restricted with its expired `retry_after` unchanged, so each following pass
costs exactly one bounded probe until Canvas answers definitively. Manual `sync_now(course_id)` bypasses the
cooldown entirely and always runs a full probe; the 15-minute heartbeat never
does. Skipped-restricted runs and circuit opens/clears are counted in
`sync_metadata`'s existing return summary (`capability`, `skipped_restricted`,
`circuit_opened`, `circuit_cleared`) so the effect is observable without
exposing course names.

## Mirror-first reads (`api/mirror/queries.py`)

Implements the `gradebook_queries` interface (`course_students`,
`course_assignments`, `course_submissions`, `assignment`,
`assignment_submissions` — each returning `(data, error)`) from the store.
Consumers flipped in v1:

- `gradebook_snapshot.load_snapshot` — mirror-first when fresh, live
  fallback; snapshot carries `source` + `synced_at` either way (web UI route
  and MCP both inherit this).
- MCP `get_roster` / `get_submissions` — served from the mirror when fresh
  (zero Canvas calls, works offline), pseudonymized and gated exactly as
  before; payloads carry `source` + `synced_at`.

Explicit `queries=` overrides and monkeypatched test seams always bypass the
mirror, so offline tests exercise the live path unchanged.

## v1 non-goals (deliberate)

- Submission **comments** are captured by the nightly full pass (author id,
  author role, comment text, created_at only — no names/avatars/attachments), so
  staleness is bounded to ~24h. Delta stays lean: comment timestamps bump
  neither `submitted_since` nor `graded_since`, so a comment-only change
  between full passes is still a blind spot until the next full pass.
- **Attachment downloads** (names only, in attempt records).
- New Quiz item-level grading or feedback writes. Mirror snapshots are
  read-only; the existing live/native grader preflight remains mandatory before
  any write.
- Multi-machine conflict smarts beyond disposability. (`vault.json` — not a
  mirror file — remains the one cross-machine-conflict-sensitive artifact.)
- Startup-item registration (separate slice; per-user Startup folder,
  no admin).
