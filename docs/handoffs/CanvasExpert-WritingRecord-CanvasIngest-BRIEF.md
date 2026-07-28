# Brief — Canvas-sourced ingest for the writing record (typed submissions)

**Active execution brief. Written 2026-07-28.** One vertical batch.
Supersedes `CanvasExpert-WritingRecord-ECRSubstrate-BRIEF.md`, GREEN and closed at `ef40e01`.

---

## 1. Objective

A teacher points CanvasExpert at one Canvas assignment and its typed student responses
enter the longitudinal writing record, pseudonymously, without hand-authoring JSON.

Today the substrate accepts extended writing (`ingest_unscored`, landed in `ef40e01`) and an
assistant can read it (`get_writing_history`, landed in `b2b89a0`), but the only way to put
anything in is a hand-built `{"reps": [...], "submissions": [...]}` file passed to
`api/dailywriting/cli/ingest.py`. Every submission in it needs a pre-resolved pseudonym and
an ISO timestamp with an explicit UTC offset. For a class of thirty that is a scripting job,
not a teacher's job, so in practice the record stays empty and everything built on it is
theoretical.

## 2. Why typed-only, and why that is still a whole slice

Extended writing reaches this teacher three ways: typed into Canvas, uploaded as DOCX, and
handwritten photos. **Handwriting is out entirely** — deferred by the teacher 2026-07-28.
**DOCX is Batch 5**, deliberately.

The split is not by convenience but by risk. Everything decision-heavy in Canvas-sourced
ingest is shared by both routes: constructing an `AssignmentContext` from an assignment that
was never authored as a rep, deriving ids that make a re-run idempotent, choosing the trigger
seam, and proving the pseudonym path end to end. None of that needs a network call, because
**typed submission text is already in the local mirror** as `body`, already pseudonymized and
scrubbed by the path `get_submissions` uses.

DOCX adds a genuinely separate problem — a live per-submission Canvas call, an unbounded
binary download, and extraction — on top of that shared substrate. Doing both at once means
debugging assignment mapping and network acquisition simultaneously. This batch makes the
pipeline real with zero new transport code; Batch 5 changes only where the text comes from.

**A live attachment fetch in Batch 5 will not violate the mirror-only law**, and that is
worth recording now so it is not re-litigated. `docs/mirror.md` Design law 6 scopes the law
to the AI-facing MCP tools — `get_roster`, `get_seating_context`, `get_submissions`,
`get_gradebook_snapshot` — whose "whole path to Canvas must stay indirect." The web UI's own
gradebook route already falls back to live Canvas labelled `source: "canvas"`, and
`api/portfolio_service.py` and `api/student_packet.py` already make focused per-submission
live calls. Ingest belongs to that category, not to the MCP one. Ingest must not be exposed
as an MCP tool.

## 3. Locked decisions

1. **Typed text comes from the mirror, not from Canvas.** No live call in this batch. If the
   mirror is stale, refuse and say so — same posture as the MCP tools, for the same reason.
2. **ECRs ingest unscored**, via `ingest_unscored`. Carried from `ef40e01`.
3. **`rep_id` and `submission_id` are derived deterministically from Canvas ids**, so a
   re-run overwrites rather than duplicates. `put_rep` already replaces in place by `rep_id`
   (`store/repo.py:225-244`). `append_submission` appends unconditionally, but every reader
   collapses on `submission_id` via `_latest_by` (`repo.py:126-136`), so a stable id makes a
   re-run read-idempotent. Derivation must be pure and documented at its definition.
4. **An unscored rep must be unmistakably unscored.** `tier` and `criteria_set_id` are inert
   on the unscored path — verified: nothing in `ingest_unscored` → `_process` →
   `segment_submission` → `observe_flags` reads either. But they become load-bearing the
   moment anyone replays the scored path, and `cli/score.py` selects criteria by **`tier`**,
   not by `criteria_set_id`. A Canvas-sourced rep carrying a plausible-looking tier would be
   silently scored against a checklist written for one-sentence reps. Pick a representation
   that makes accidental scoring impossible rather than merely unlikely, and make
   `cli/score.py` refuse such a rep loudly. Do not leave this to a comment.
5. **`prompt_text` comes from the catalog's `description_text`**, which is already
   HTML-stripped at catalog-build time (`api/course_catalog.py:64-104`). Do not re-strip and
   do not reach for raw HTML — but note `get_course_assignments` truncates to a preview
   unless `full_descriptions=True` (`api/mcp_server/tools.py:376`), and a truncated prompt
   stored as the durable record of what a student wrote against is a silent corruption.
6. **Nothing in this batch writes to Canvas**, exposes an MCP tool, or changes scoring,
   segmentation, the store, the codec, or `projection.py`.

## 4. Scope and insertion points

| Change | File | Note |
|---|---|---|
| Canvas assignment → `AssignmentContext` | new, `api/dailywriting/canvas_source.py` (executor's call on name) | The one place the mapping in §5.1 lives. Pure: takes already-read catalog/mirror dicts, returns a context. No I/O, no Canvas import — AC8 of the read-path batch still applies. |
| Deterministic id derivation | same module | `rep_id` from course + assignment; `submission_id` from assignment + student canvas id (+ attempt, if resubmission must be distinguishable — decide and document). |
| Ingest driver | new, alongside the above | Reads mirror submissions, resolves pseudonyms through the existing vault, calls `ingest_unscored`, writes through `Repository`. Refuses on a stale mirror. |
| Teacher trigger | `api/webui/routes/` | Follow the SSE-streamed-generator precedent: `api/webui/routes/reports.py:283-341` and `portfolio_service.build_merged_portfolios`. **Not** `api/work_registry/` — it is a display-only projection and its `source_ref` schema structurally forbids student-identifying keys (`work_registry/models.py:117`). |
| CLI parity | `api/dailywriting/cli/` | A command wrapping the same driver, so the path is testable without the web UI. |
| Product guide | the `writing_record` topic + its served file | How work enters the record. One canonical text. |

Out of scope in these files: `core/scoring.py`, criteria JSON, `thresholds.py`, the store,
the codec, `projection.py`, and anything under `api/mirror/`.

## 5. The mapping, decision by decision

Only `prompt_text` has a real Canvas source. Every other required field is a decision, and
the executor must make each one explicitly and record it in §12 rather than picking silently.

1. **`date`** — from `due_at`, `unlock_at`, or `created_at`; a tz-aware datetime must become
   a plain school-day date, and the chosen field can be null. State the fallback chain.
2. **`section_id`** — **a Canvas assignment carries no section.** `ASSIGNMENT_KEYS` has
   `assignment_group_id`, a grading category, not a section; sections exist only on the
   roster. Either leave it `None` — which quietly opts every Canvas-sourced rep out of
   `Repository.reps(section_id=...)` filtering — or fan out one rep per section, multiplying
   reps per assignment. Both are defensible; pick one and say why.
3. **`tier` / `criteria_set_id`** — see §3.4.
4. **`scaffold_blocks`, `source_texts`, `word_cap`** — default empty/`None`. Do not attempt
   to parse them out of description prose. A wrong scaffold changes segmentation, and a
   guessed `{{BLANK}}` is worse than none.
5. **Re-ingest of an edited assignment** — if the description or due date changed, `put_rep`
   overwrites. Confirm that cannot retroactively invalidate stored work:
   `scoring.assert_criteria_published` compares criteria `published_at` against the context
   `date` (`core/scoring.py:552`), so a changed `date` is not inert for any rep that ever
   gets scored.

## 6. Acceptance criteria

1. For a course whose mirror holds a text-entry assignment with submissions, one command
   ingests every typed submission and `get_writing_history` returns them for the right
   pseudonyms, in date order, with no `Score`.
2. Running the same ingest twice produces the same `get_writing_history` output — same
   submission count, no duplicates. Assert on the tool's output, not on file contents.
3. No real name, Canvas id, SIS id, or section appears in the store or in any payload.
   `feedback_safety.scan_payload(result, vault)["green"] is True` **and** `["soft"] == []`
   for a fixture roster whose real names appear in the submitted text. The `soft` assertion
   is not optional — a roster name in free text is a soft finding, so `green` alone cannot
   detect a name leak.
4. A stale or missing mirror produces a structured refusal naming the remedy, not a partial
   ingest and not an exception.
5. A student in the mirror with no vault entry is refused by name of the remedy
   (roster sync), and does not abort the ingest of everyone else. State which behaviour you
   chose — skip-and-report or refuse-all — and why.
6. A Canvas-sourced rep cannot be scored by accident: `cli/score.py` (or whatever the scored
   path is) refuses it with a message naming the reason. Test the refusal.
7. An assignment whose `description_text` is empty still ingests, and the empty prompt is
   visible as empty rather than silently becoming `""`-that-looks-authored.
8. No new module under `api/dailywriting/` imports `api.canvas`, `requests`, or any Canvas
   transport. The driver reads already-fetched mirror data.

## 7. Named verification gate

```bash
python -m pytest api/tests/dailywriting api/tests/test_mcp_server_tools.py -q
```

Plus the full `api/tests` suite. Two Windows long-path failures
(`test_feedback_pipeline.py`, `test_powergrader_packet.py`) are the environmental baseline;
`test_beta075_storage.py::test_spawned_vault_writers_preserve_both_students` is
load-sensitive and appears only under full-suite contention.

**Additionally required, because a green suite is evidence about tests and not about
behaviour:** diff `student_word_count` and segment origins across the whole
`singles.json` fixture corpus before and after your change and report the result. Two
batches in a row have shipped silent behaviour changes that the suite did not catch. The
pinned-fixture test added in `ef40e01` covers segmentation; extend the same discipline to
anything you touch.

Proportional manual check: this batch adds a web route. Load it, exercise it once against a
fixture mirror, and confirm zero new browser console errors.

## 8. Open decision — the senior must answer before merge

**Which assignments feed the writing record.** Asked and not yet answered.

The teacher's first answer was "reuse the existing tracked choice," which turned out to rest
on a false premise: `is_tracked_assignment` (`api/powergrader/writing_timeline.py:56`) is not
a stored flag but a structural classifier — `submission_types == {"online_upload"} and
allowed_extensions == {"docx"}`. A typed text-entry submission can never satisfy it, so
reusing it would permanently exclude this batch's only route, and the served Writing Record
guide already states "This has nothing to do with Writing Timeline."

Options, with the senior's recommendation first:

1. **The ingest action is the opt-in.** No persistent flag; pointing at an assignment is the
   decision. Zero new state, no staleness, no cleanup. Recommended: with one user and no
   evidence about how often assignments need picking up, a flag is state to maintain before
   knowing it is wanted, and option 2 stays available later without rework.
2. **A Canvas assignment group.** Read `assignment_group_id`, which the catalog already
   stores. Same philosophy as `is_tracked_assignment` — derive from ordinary Canvas state —
   but works for every submission type, and enables automatic pickup later.
3. **A real per-assignment flag** owned by CanvasExpert. Most explicit, but it is the new
   store, UI, and staleness handling the other two avoid.

**Build against option 1.** It is the only one that requires no mechanism, so options 2 and 3
remain reachable from it. If the teacher chooses otherwise, the change is at the selection
boundary, not through the batch.

## 9. Follow-on batches

- **Batch 5 — DOCX acquisition.** A live per-submission fetch
  (`submission_transport.fetch_submission`, no `include[]`, returns `None` on any failure),
  `download_binary`, and `student_attachments._docx_segments` for extraction. Three gaps to
  close first: `download_binary` has **no size cap, no content-type check, and no
  signed-URL-expiry handling** (`api/submission_transport.py:24-31`) — tolerable for one
  report, not for a whole class unattended. Note PDF is `LOCAL_ONLY_EXTS` on the
  `student_attachments` path and is extracted only in `api/portfolio.py`; if ECRs ever arrive
  as PDF that is a further gap.
- **Batch 6 — handwriting**, if the teacher revives it. Requires local OCR: an image cannot
  be scrubbed by a text scrubber, so whatever performs OCR sees the unscrubbed name at the
  top of the page, and a third-party service would breach INV-7 before any guardrail acts.
- **Batch 7 — pseudonym format and scrub correctness.** Unchanged; not time-pressured.
- **Batch 8 — teacher-facing longitudinal report**, extending `api/portfolio_service.py`.
- **Release gate before any of this reaches a live student:** the Appendix E rewrite. E
  describes pseudonymization of names and ids; it does not describe durable
  cross-assignment retention of student writing. A gate, not documentation cleanup.

## 10. Stop conditions

Return YELLOW rather than guessing if:

- a required `AssignmentContext` field has no defensible derivation and §5 does not cover it;
- making an unscored rep unscorable (§3.4) requires changing a store model or the codec;
- the mirror does not actually carry typed submission text for a real assignment shape.

Return RED if a live Canvas call, a Canvas write, or an MCP tool appears necessary — that
contradicts §2 and §3 and the batch is mis-scoped.

## 11. References (section-routed; do not read wholesale)

- `AGENTS.md` — *Non-negotiable guardrails*, *Executor responsibilities*, *Lean engineering
  defaults*.
- `api/dailywriting/__init__.py` — the seven invariants. Short, read in full.
- `api/dailywriting/core/ingest.py` — `ingest_unscored` and `_process`.
- `api/dailywriting/store/repo.py` — `put_rep` :225, `_latest_by` :126, `append_submission`
  :156, `Repository.default` :84.
- `api/course_catalog.py` — `ASSIGNMENT_KEYS` :37, `_description_text` :95,
  `normalize_assignment` :340.
- `api/webui/routes/reports.py:283-341` and `api/portfolio_service.py:64-79` — the SSE
  generator precedent for slow per-course work.
- `docs/mirror.md` — *Design law 6*, which scopes the mirror-only law to MCP tools.
- `docs/reference/project-state.md` — pre-launch, 0 users, 1 through ~Dec 2026.
- Closed briefs, in Git history: read-path at `b2b89a0`, ECR substrate at `ef40e01`
  (`git show <hash>:docs/handoffs/<name>`). The ECR brief's §8.1 carries the unfixed
  paragraph-break span defect in `core/scoring.py` and the measured segmentation-performance
  dead end.

## 12. Execution result

**GREEN.** Not committed (per boundaries) — working tree at parent commit `348411a` plus
the changes below, left for review.

### Changed / added files

- `api/dailywriting/canvas_source.py` (new) — pure mapping: `AssignmentContext` from a
  catalog assignment record, `rep_id_for`/`submission_id_for` deterministic ids,
  `UNSCORABLE_TIER`/`UNSCORABLE_CRITERIA_SET_ID` sentinels, `is_unscorable()`.
- `api/dailywriting/canvas_ingest.py` (new) — the driver: reads the course catalog +
  CanvasMirror, refuses (`CanvasIngestError`) on missing catalog/assignment or a
  stale/missing mirror, syncs the roster into the vault, calls `ingest_unscored` per typed
  submission, writes through `Repository`. Generator of progress strings.
- `api/dailywriting/cli/ingest_canvas.py` (new) — CLI wrapper over the same driver.
- `api/dailywriting/cli/score.py` — added the explicit `canvas_source.is_unscorable(context)`
  refusal before `criteria_for()`, with a message naming the reason.
- `api/webui/routes/dailywriting.py` (new) — `POST /api/dailywriting/ingest-canvas`,
  consumes the driver generator into one JSON response (`{ok, log}` /
  `{ok: false, error, log}`), same shape as `portfolio_merged` (`routes/reports.py:283-341`).
- `api/webui/server.py` — registered the new router.
- `api/default_docs/AI Authoring/Writing Record (longitudinal writing history).txt` — added
  "How work enters the record" (the served `writing_record` guide topic; single canonical
  text, no second copy).
- `api/tests/dailywriting/test_dw_canvas_ingest.py` (new) — 16 tests, see below.
- `api/tests/test_route_contract.py` — added the new frozen route (the test's own stated
  purpose: a deliberate, reviewed surface change).

### Commands and counts

```
python -m pytest api/tests/dailywriting api/tests/test_mcp_server_tools.py -q
=> 222 passed
python -m pytest api/tests -q
=> 2 failed, 1570 passed
   (test_feedback_pipeline.py::test_write_safe_and_private_auto_detects_compact_on_deep_path,
    test_powergrader_packet.py::test_packet_workflow_budget_exception_stops_before_writes --
    exactly the two declared Windows long-path baseline failures, nothing else)
```

Before `test_route_contract.py` was updated, the full run showed a third failure
(`test_route_contract`) — expected, since it is the deliberate-edit tripwire the new route
is supposed to trip; fixed in the same batch, not a leftover.

### Fixture-corpus diff (§7)

Computed `{student_word_count, sorted origin set}` for every `singles.json` fixture via
`segmentation.segment_submission`, before touching any file and again after the full
change: **byte-identical**, both matching the existing pinned values in
`test_dw_segmentation.py` (`_EXPECTED_FIXTURE_RESULTS`). Expected — nothing in this batch
touches `core/scoring.py`, `core/segmentation.py`, `core/scrub.py`, `core/models.py`, the
store, or the codec — but computed rather than assumed, per the instruction.

### Each §5 decision, as made

1. **`date`** — `due_at`, then `unlock_at`, then `created_at` (`canvas_source.rep_date`).
   In that order because that is how much each one means "when this was assigned as a
   school day"; `created_at` is a last resort (record-authored time, not assignment time,
   but still real). If none of the three parse, **refuse** (`DateDerivationError` ->
   `CanvasIngestError`) rather than fabricate "today": `date` is what `get_writing_history`
   sorts on, and an invented date is a silent corruption of that ordering.
2. **`section_id`** — left `None`. A Canvas assignment carries no section; fanning out one
   rep per roster section was the alternative, but nothing yet consumes
   `Repository.reps(section_id=...)` for Canvas-sourced work, so `None` opts these reps out
   of that filter reversibly, cheaper than a fan-out with no current reader.
3. **`tier` / `criteria_set_id`** — `UNSCORABLE_TIER = 0` / `UNSCORABLE_CRITERIA_SET_ID =
   "unscored:canvas-typed"`. Both are real `AssignmentContext` field types (`int`, `str`),
   so no store model or codec change was needed. `cli/score.py` now checks
   `canvas_source.is_unscorable(context)` explicitly and refuses with a message naming the
   reason, before `criteria_for()`/`assert_criteria_published` are ever reached — which is
   also why an edited assignment's changed `due_at` (§5.5) can never retroactively
   invalidate a Canvas-sourced rep: the comparison it would invalidate is never run on this
   rep at all.
4. **`scaffold_blocks`, `source_texts`, `word_cap`** — empty/`None`, exactly as directed;
   no attempt to parse a stem or a word cap out of description prose.
5. **Re-ingest of an edited assignment** — confirmed inert: see point 3. `put_rep` still
   overwrites in place by `rep_id` (unchanged, deterministic), so a re-run reflects the
   latest catalog state, but a Canvas-sourced rep can never reach
   `scoring.assert_criteria_published` regardless of what `date` says.

### AC5 behaviour: skip-and-report, not refuse-all

A submission whose author has no identity-vault entry after the full roster sync (an
edge case — enrolled-but-unsynced is normal; submitted-but-not-on-the-current-roster is
not) is skipped and counted (`no_identity`), not raised. Rationale: an assignment's
submission list can include one anomalous student (roster drift, a dropped/late add)
without that one gap being a reason to withhold every other enrolled student's rep for the
day. `CanvasIngestError` (refuse-all) is reserved for conditions that make the whole
read untrustworthy (no catalog, no such assignment, stale/missing mirror) — never for one
student's identity gap. Tested in `test_unknown_author_is_skipped_and_reported_not_fatal`.

### Manual web-route check (§7)

Read-only verification server (`py -m uvicorn api.webui.server:app --lifespan off`, port
8766, via the existing `canvas-expert-verify` launch config). The real machine config
(`%LOCALAPPDATA%\CanvasExpert\config.json`) was temporarily pointed at a scratch
workspace seeded with fabricated catalog + CanvasMirror fixture data (fake "Learner
One"/"Learner Two" roster, never real district data), then restored byte-for-byte
immediately after — verified by diff. Real OneDrive workspace was never touched.

- Home (`/`) loaded with zero console/server errors.
- `POST /api/dailywriting/ingest-canvas` (course 111 / assignment 700010) via `fetch()`:
  `{"ok": true, "log": ["rep canvas:111:700010 stored: ...", "<pseudonym>: ingested, 9
  student word(s)", "<pseudonym>: ingested, 5 student word(s)", "2 submission(s)
  ingested..."]}`, HTTP 200, zero new console/server errors.
- Re-running the identical request returned the same two pseudonyms and the same counts
  (idempotent re-run over real HTTP, not just in-process).
- An unknown `assignment_id` returned a structured `{"ok": false, "error": "No assignment
  999999..."}`, HTTP 200, no server exception, zero console errors.

### Deviations from a literal reading of the brief

- The web route is a plain `POST` JSON endpoint with no dedicated UI page/button yet. §4's
  insertion-point table names only `api/webui/routes/`, not a template/JS file, and the
  cited precedent (`portfolio_merged`) is itself the same shape (a route consuming a
  progress-string generator into one JSON response) rather than literal SSE. Wiring a
  course/assignment picker into an existing page (Course Info reads live Canvas, not the
  catalog/mirror this batch reads, so it was not a clean fit) was judged out of scope for
  this batch; flagging as a candidate follow-on if the teacher wants a button rather than
  an API call.
- The route does not gate on `active_courses()`/"Current courses," matching
  `portfolio_merged`'s convention for web routes (unlike the MCP tools' `_course_gate_check`);
  the brief did not call this out as a required gate for this batch.
- `AssignmentContext.tier` (0) is exposed as-is in `get_writing_history`'s `tier` field for
  a Canvas-sourced rep (faithful to what is stored, not hidden) — flagged here since it is
  a visible, if harmless, side effect of the sentinel choice.

### Unresolved

None found during execution; §8 (which assignments feed the record) was pre-decided by the
senior as option 1 (the ingest action is the opt-in) and built accordingly.
