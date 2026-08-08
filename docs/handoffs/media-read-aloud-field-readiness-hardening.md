# Media/read-aloud field-readiness hardening

**Status:** COMPLETE — GREEN
**Branch:** `dev`
**Expected starting commit:** `385c0a98207ab9212b4b0773322a60d6cd32e4cd`
**Risk:** Medium — private local evidence and PowerGrader session assembly change, but no
Canvas write, external AI contract, credential path, or live-course verification is authorized.

## Objective

Make ordinary Canvas media submissions reliably reviewable before a live course exists:

1. one unrelated unsubmitted/held row cannot block playback of a complete recording;
2. an exact cached recording remains playable on later sessions;
3. media review works without read-aloud analysis, while read-aloud is an explicit
   default-off teacher choice; and
4. one read-aloud run loads the local speech model at most once and alignment no longer
   allocates a Python integer matrix proportional to passage words × transcript words.

This is one vertical hardening batch. Use only synthetic data, injected speech adapters, and
the already-installed repository/runtime capabilities. Do not install or download anything.

## Teacher-visible outcome

- A teacher can open and play each complete local Canvas recording even when another student
  has not submitted or another evidence item is held.
- Reopening the assignment plays an integrity-verified reused recording exactly like a newly
  downloaded one.
- The setup surface defaults to ordinary local media review. Selecting **Read-aloud analysis**
  reveals and requires the confirmed passage and local-model controls; leaving it off neither
  validates a passage nor invokes speech analysis.
- A non-read-aloud media session reaches the same teacher queue with local playback and no
  oral-reading report. Existing scoring/write restrictions for any media session remain intact.

## Required preflight — run before writing

1. Read repository `AGENTS.md`, then this brief.
2. Read only these routed references:
   - `docs/reference/project-state.md` → **Status: pre-launch**, **Userbase: 0 today, 1 for
     the first semester**, and **What this means for scope**;
   - `docs/reference/powergrader-module-map.md` → **Entry points**, **Ownership routes**,
     **Privacy and write boundaries**, **Symptom routing**, and **Test routing**;
   - `api/webui/README.md` → **Rendered verification (read-only)**, **PowerGrader module
     routing**, and **PowerGrader (`/powergrader`)**;
   - `docs/reference/webui-presentation-system.md` → **Who these pages are for**, **Page
     conventions**, **CSS ownership**, and **Change propagation**;
   - `docs/contracts/oral-reading-evidence-contract.md` in full;
   - `docs/handoffs/senior/media-recording-read-aloud-initiative.md` → §§3.1, 3.3, 3.10,
     4 (only the ownership table and anti-abstraction paragraph), 6, 10, 11, and 15.
3. Run:

   ```powershell
   git fetch origin dev main
   git status --short --branch
   git rev-parse HEAD
   git rev-parse origin/dev
   git rev-list --left-right --count origin/main...HEAD
   ```

4. Confirm branch `dev`; `HEAD` equals `origin/dev`; and these known user changes are the only
   overlapping worktree context:
   - `Open Canvas Expert.bat`
   - `Repair.bat`
   - `api/default_docs/AI Authoring/START HERE - CanvasAgent.txt`

   Preserve them byte-for-byte and do not stage them. Stop if a newer change overlaps any file
   authorized below or if repository truth contradicts a locked decision.
5. Confirm these insertion points still exist:
   - `assignment_refresh.refresh_assignment`
   - `powergrader.pg_media_stream` and `powergrader.pg_start`
   - `canvas_fetch.ingest_media_recordings` producing `downloaded`/`reused`
   - `oral_reading.align`, `oral_reading.analyze_recording`, and its injected `transcribe` seam
   - `session_builder._attachment_metadata` and `session_builder.build_session`
   - `setup_core.js::bindStartSession`
   - `queue_media_recording.js::renderMediaRecordings`

The absence of `faster-whisper`, `ctranslate2`, or model weights is expected and is not a failed
preflight. Do not run a model setup route, package installer, dependency installer, or live
Canvas request.

## Locked decisions

### 1. Manifest completeness and playback are different questions

- An unsubmitted row (`workflow_state == "unsubmitted"` or no actual `submission_type`) does not
  make an otherwise complete focused evidence manifest `incomplete` merely because its attempt
  is absent.
- A submitted/evidence-bearing row still requires user identity, attempt identity, expected
  evidence identity, successful acquisition, and required media hashes/paths. Conflicts,
  budget failures, failed downloads, missing evidence, and New Quiz errors remain incomplete.
- Playback authorization is per evidence record, not an all-or-nothing use of manifest
  `status`. A valid media record may stream from an `incomplete` manifest when the incompleteness
  belongs elsewhere.
- The stream route must still bind session owner + course + assignment + media evidence ID,
  enforce workspace containment, require the canonical relative path and digest, verify the
  current file digest, send no private path/Canvas URL, and fail closed for missing, mismatched,
  escaped, or tampered evidence. Do not relax these checks.

### 2. Reuse is a ready state

- `download_status in {"downloaded", "reused"}` plus
  `extraction_status == "validated"` is locally playable.
- Every other acquisition/extraction state remains visibly held.
- Do not rewrite `reused` to `downloaded`; reuse is meaningful evidence provenance.

### 3. Read-aloud is explicit and default-off

- Add one setup checkbox named `oral_reading_enabled`, unchecked on every page load and not
  sticky across assignments or sessions. Do not infer intent from a nonempty passage, assignment
  title/description, rubric, submission media type, or prior session.
- When unchecked, passage/model controls are hidden and disabled, the form explicitly posts
  false, the backend does not validate the passage, inspect model readiness, construct a model,
  or call a transcriber, and media remains available for local teacher review.
- When checked, passage/model controls are visible. After focused refresh confirms at least one
  submitted ordinary `media_recording`, the current 1–3,000 normalized-English-word passage law
  applies. If no submitted media recording exists, return a specific actionable start error
  instead of silently ignoring the choice.
- Persist the clean current session truth in the existing `oral_reading_passage` block:
  `{ "enabled": false }` when off; `{ "enabled": true, "passage": ..., "digest": ... }`
  when on. There is no legacy reader, dual shape, migration, or compatibility fallback.
- Only selected read-aloud media receives `oral_reading` reports. Queue rendering for ordinary
  media remains the player/status surface and does not invent an empty report.
- All existing prohibitions on media auto-post and late catch-up remain unchanged.

### 4. One model construction per read-aloud run

- Keep `api/powergrader/oral_reading.py` Canvas-free, LLM-free, and independently injectable.
- Add one narrow local-transcriber construction seam in that module. `pg_start` constructs it
  once after explicit read-aloud selection and valid passage/media are known, then passes the
  same callable to every `analyze_recording` call in that run.
- Model status/import/construction failure is attempted once and produces the existing
  content-minimized `unavailable` report for each affected recording. Starting grading never
  downloads weights and never reaches the network.
- Preserve direct injected-transcriber tests. Do not create a provider registry, adapter
  hierarchy, background worker/service, progress framework, model pool, or second runtime.

### 5. Compact deterministic alignment

- Preserve the current normalization, exact/substitution/omission/insertion tie order,
  accuracy/WCPM rules, confidence threshold, candidate cap, timestamps, and report vocabulary.
- Replace the `(source + 1) × (observed + 1)` Python integer cost matrix with two numeric cost
  rows plus compact one-byte-per-cell backpointers (or an equally small implementation with the
  same explicit bound). At the 3,000-word limit there must be no quadratic matrix of Python
  integer objects.
- Time remains deterministic dynamic programming; this batch does not add concurrency or claim
  a real-machine throughput result.

## Acceptance criteria

1. A synthetic focused refresh containing one complete submitted media row plus one unsubmitted
   row with no attempt writes/returns `status == "current"` and preserves the complete evidence.
2. A submitted row with missing attempt/identity, failed media acquisition, missing hashes/path,
   conflict, or budget failure still makes the manifest incomplete as applicable.
3. `pg_media_stream` returns playable WAV bytes for a valid session-owned record even when the
   manifest has an unrelated `incomplete` status; wrong owner/key, missing record/path/digest,
   workspace escape, missing file, and digest mismatch remain 404/409 fail-closed cases.
4. Queue behavior renders an audio player for both validated `downloaded` and validated `reused`
   records, and renders held state for every other status combination. Reused playback still uses
   only the session-scoped stream URL.
5. With read-aloud off, a submitted media recording starts a local-review session without a
   passage and without calling model status, model construction, or transcription. Its session
   block is exactly `{ "enabled": false }`, and its queue shows playback with no reading report.
6. With read-aloud on, missing/invalid passage and no-submitted-media cases return distinct,
   actionable errors; valid media uses the normalized passage and persists enabled/passage/digest.
7. A synthetic run with at least three recordings proves exactly one local model construction
   and three calls through the same injected transcriber. A construction failure is attempted
   once, performs zero network/download actions, and yields one unavailable report per recording.
8. Alignment behavior remains identical for the existing exact, substitution, omission,
   insertion, repetition, self-correction, confidence, duration, reuse-binding, and difference-cap
   cases. Implementation inspection confirms two cost rows plus compact backpointers and no
   quadratic Python-int matrix.
9. `/powergrader` and a synthetic `/powergrader/session/{id}` render at 1440×900 and 390×844 in
   light and dark themes. Verify checkbox/passage visibility and keyboard operation, fresh and
   reused playback controls, student navigation stopping prior audio, no horizontal page overflow,
   required globals/load order, and zero new console errors or warnings. Use a lifespan-disabled
   local server and synthetic temporary workspace/session only; do not start a scoring session or
   make Canvas/AI calls during visual verification.
10. No test or committed artifact contains a real name, ID, recording, URL, credential, private
    path, downloaded model, or developer-specific absolute path.
11. The exact documentation sections named below describe ordinary media review as the default,
    read-aloud as explicit, `downloaded`/`reused` as playable, per-record stream readiness, and
    one model construction per selected run. Do not alter the current transcript/SAFE policy.

## Authorized implementation surface

Production:

- `api/powergrader/assignment_refresh.py`
- `api/powergrader/oral_reading.py`
- `api/powergrader/session_builder.py`
- `api/powergrader/start_workflow.py`
- `api/webui/routes/powergrader.py`
- `api/webui/templates/powergrader_setup.html`
- `api/webui/static/powergrader/setup_core.js`
- `api/webui/static/powergrader/queue_media_recording.js`
- `api/webui/static/powergrader_queue.css` only if existing checkbox/show-hide layout utilities
  cannot express the state; add no palette/type/radius/shadow literals.

Tests:

- add `api/tests/powergrader/test_assignment_refresh.py` for the owner-level manifest laws;
- update `api/tests/powergrader/test_media_recordings.py`;
- update `api/tests/powergrader/test_oral_reading.py`;
- add `api/tests/webui/routes/test_powergrader.py` for start/stream route behavior;
- update only directly affected cases in `api/tests/test_powergrader_attachment_workflow.py`,
  `api/tests/test_route_contract.py`, and `api/tests/test_webui_template_contracts.py`.

Documentation:

- `docs/contracts/oral-reading-evidence-contract.md` — selection/default-off semantics only;
- `docs/reference/powergrader-module-map.md` — **Ownership routes**, **Privacy and write
  boundaries**, **Symptom routing**, and **Test routing** only;
- `api/webui/README.md` — **PowerGrader (`/powergrader`)** only;
- `docs/handoffs/senior/media-recording-read-aloud-initiative.md` — §§3.1, 3.3, 3.10, 4
  ownership table, 6, 10.3, and 11 only;
- this brief's **Execution result**.

Do not touch any other file without stopping for senior direction. Use function-style tests;
each new test must be a direct law, a boundary contract, or the single batch example. Do not add
test classes or redundant wrapper tests.

## Explicit non-goals

- No blind-first changes.
- No reconciliation or modification of transcript/SAFE/AI privacy behavior, packet contents,
  teacher disclosure language beyond what is strictly necessary to expose the read-aloud choice,
  `feedback_artifacts.py`, `ai_workflow.py`, packet/Copilot/MCP owners, or scoring-result contracts.
- No live Canvas request, dummy-course creation, submission, grade/comment write, or write preflight.
- No package/software/model installation or download; no `PATH`, environment, launcher,
  requirements, or credential changes.
- No new media source, New Quiz/Classic Quiz/Studio/discussion/external-tool support.
- No codec/tenant transport claim, speech-accuracy claim, real CPU benchmark, streaming progress
  UI, parallel downloads/transcription, worker pool, scheduler, or job persistence.
- No migration or compatibility code for pre-launch session/manifest shapes.

## Named verification gate

Run the focused deterministic gate from the repository root:

```powershell
py -m pytest api/tests/powergrader/test_assignment_refresh.py api/tests/powergrader/test_media_recordings.py api/tests/powergrader/test_oral_reading.py api/tests/webui/routes/test_powergrader.py api/tests/test_powergrader_attachment_workflow.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py api/tests/test_feedback_pipeline.py -q -p no:randomly --tb=short
```

Then perform the rendered verification in acceptance criterion 9 using the lifespan-disabled
command in `api/webui/README.md`. Do not run the full API suite unless a focused failure reveals
unexpected cross-cutting coupling. Do not rerun a successful gate unless the relevant diff changes
or evidence is missing.

Before reporting, inspect the complete diff and run:

```powershell
git status --short
git diff --check
```

## Stop conditions

Return RED without broadening scope if:

- Canvas media playback cannot remain authorized by a single manifest evidence record without
  weakening session ownership, workspace containment, or digest verification;
- current manifest consumers require an assignment-wide `current` status for a reason not named
  in the routed references;
- ordinary local media review cannot reach the queue without changing SAFE/AI packet contracts;
- explicit read-aloud selection requires a new persistence registry, background service, or
  public API contract;
- preserving alignment semantics requires changing scoring/reading rules rather than storage;
- a dependency import/model construction cannot be isolated behind the existing injected seam;
- any required check would install/download software, call live Canvas/AI, or expose private data;
- an authorized file has overlapping user changes, an out-of-scope regression appears, or a
  public contract outside the authorized sections must change.

## Execution result

**Traffic light:** GREEN.
**Commit:** landing commit (this commit)
**Changed files:** `api/powergrader/assignment_refresh.py`, `api/powergrader/oral_reading.py`, `api/webui/routes/powergrader.py`, setup/queue media UI files, focused tests, and the authorized documentation sections.
**Verification:** `py -m pytest api/tests/powergrader/test_assignment_refresh.py api/tests/powergrader/test_media_recordings.py api/tests/powergrader/test_oral_reading.py api/tests/webui/routes/test_powergrader.py api/tests/test_powergrader_attachment_workflow.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py api/tests/test_feedback_pipeline.py -q -p no:randomly --tb=short` — **127 passed**. `git diff --check` passed. Senior rendered `/powergrader` and `/powergrader/session/synthetic-media-session` on a lifespan-disabled synthetic server at 1440×900 and 390×844 in light/dark: no horizontal overflow, setup default-off and keyboard-ready, fresh/reused session streams played, navigation stopped/replaced audio, ArrowLeft navigation worked, no ordinary-media oral report, correct script order, and zero console warnings/errors.
**Deviations:** no Canvas, AI, model setup/download, or live-course access.
**Unresolved decisions:** none.
