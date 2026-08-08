# Media-recording read-aloud, Batch A: private acquisition and review

**Status:** RED, preflight blocked. No implementation source edits are authorized until the
teacher-owned dummy Canvas media read below is complete.

**Baseline:** `dev`, `origin/dev`, `main`, and `origin/main` all resolve to
`450e97ffd97e6312adc185b535ae46cd7b8cbf81` as of 2026-08-07. Preserve the unrelated
user changes in `Open Canvas Expert.bat`, `Repair.bat`, and
`api/default_docs/AI Authoring/START HERE - CanvasAgent.txt`.

## Objective

A submitted ordinary Canvas `media_recording` opens in PowerGrader with a playable local
recording or a stable held reason. It must never become empty, eligible work. This batch
does not transcribe, score, create SAFE audio, or send audio outside the computer.

## Locked decisions

- Read the actual `submission_type`; support only ordinary `media_recording` submissions.
- Accept Canvas audio and video, retain one private original, and derive canonical PCM16,
  mono, 16 kHz WAV with timing intact and metadata stripped. Do not analyze video frames.
- URLs, Canvas authorization, cookies, and signed sources stay in memory only and never
  reach evidence JSON, session/browser payloads, logs, receipts, fixtures, or errors.
- One submitted media item has one exact private evidence expectation. `current` requires
  all expected evidence finalized and digest-bound. Reuse requires matching stable identity
  or content indicator plus verified existing bytes.
- Respect the separate limits: 100 MiB per student, 15 minutes per recording, 500 MiB per
  class run, and at most two concurrent media downloads or conversions. Stream to `.partial`
  then verify and atomically finalize. Never truncate or substitute media.
- A local, session-addressed audio route is the only browser access path. It must enforce
  workspace containment, session/student ownership, complete evidence, MIME/Range support,
  and no-cache headers. Never expose a path to browser JavaScript.
- Media sessions cannot enable interactive auto-post. Packet and assisted modes retain media
  students in the teacher queue with a clear analysis-unavailable state.
- Do not introduce a media registry, general transcription feature, second write owner,
  result format, migration, or compatibility path.

## Required preflight, current evidence

1. **BLOCKED, requires user-directed live read.** The teacher must create or identify a
   dummy ordinary Canvas media-recording submission containing no real student data, then
   authorize one read. Record only a sanitized structural trace: present keys, content
   types, byte sizes, redirect-host class, and status codes. Do not retain the URL, media,
   media ID, course ID, user ID, or token.
2. Prove whether `submission.media_comment.url` downloads directly. If it does not, record
   the exact permitted Canvas Media Objects endpoint/source selection and permission result.
   Prove a signed cross-origin download does not receive Canvas authorization.
3. **GREEN:** local `ffmpeg` and `ffprobe` are present (`7.1-full_build-www.gyan.dev`).
4. **GREEN:** an isolated temporary Python 3.14 environment installed and imported
   `faster-whisper 1.2.1`, `ctranslate2 4.8.1`, and dependencies. No model weights were
   downloaded; do not add this dependency to requirements in Batch A.

Until items 1 and 2 pass, stop RED. Do not scrape player/SpeedGrader HTML, forward Canvas
credentials to an untrusted host, retain a browser cookie, install system software, change
`PATH`, or retrieve a real submission.

## Authorized implementation after a GREEN live preflight

One Luna implementation executor may edit only these surfaces and must use the existing
ordinary-attachment transport as a sibling pattern, not a media-as-attachment shim:

- New `api/powergrader/media_recordings.py` for Canvas-free normalization, stream validation,
  private finalization, canonical conversion, hashes, duration, and held reasons.
- `api/powergrader/canvas_fetch.py`: `_acquire_ordinary_submissions`,
  `_download_canvas_attachment`, and `ingest_ordinary_attachments` only, adding a sibling
  media-comment acquisition path with same-host authorization and off-host HTTPS without it.
- `api/powergrader/assignment_refresh.py::refresh_assignment` for private manifest integration
  and the separate media budget.
- `api/powergrader/session_builder.py::_attachment_metadata` and `build_students`, plus
  `api/powergrader/student_attachments.py::eligibility_decision`, to fix the zero-expected
  eligible state and project only review-safe private metadata.
- `api/webui/routes/powergrader.py::pg_start` and one new stream route, including the
  media-session interactive-auto-post block. Add route registration and contract coverage.
- `api/webui/templates/powergrader_queue.html` load order, `queue_core.js::renderStudent`, and
  one new `api/webui/static/powergrader/queue_media_recording.js` feature file. Keep the queue
  shim thin and preserve existing namespace seams.
- New `api/tests/powergrader/test_media_recordings.py`, plus scoped additions to
  `api/tests/test_powergrader_attachment_workflow.py` and `api/tests/test_route_contract.py`.
- `docs/reference/powergrader-module-map.md`, and `api/webui/README.md` only if script load
  order changes.

Do not edit the user-owned `START HERE - CanvasAgent.txt`. Do not touch late catch-up unless
the named current data shape cannot otherwise be preserved; it must not run late media AI.

## Acceptance criteria

1. Synthetic audio media produces exactly one private evidence record, and synthetic video
   retains its private original while producing audio-only canonical WAV.
2. URL/auth values survive nowhere, including normalization, manifest, session, errors, or UI.
3. Missing ID/source, expired URL, redirect failure, size overflow, interrupted transfer,
   invalid container, no audio track, excessive duration, and missing ffmpeg have stable holds.
4. A submitted media recording has a nonzero evidence expectation, and manifest `current`
   requires every expected finalized, digest-bound item.
5. The queue plays canonical local audio, shows duration/status, and sends no filesystem path.
6. The stream route rejects traversal, wrong session/student ownership, incomplete evidence,
   and paths outside the workspace.
7. Score-myself remains usable. Assisted and packet modes show analysis unavailable rather than
   score an empty response; interactive auto-post is unavailable.

## Verification gate

```powershell
py -m pytest api/tests/powergrader/test_media_recordings.py api/tests/test_powergrader_attachment_workflow.py api/tests/test_route_contract.py -q -p no:randomly --tb=short
```

Render `/powergrader` and a synthetic media queue session through the read-only lifespan-disabled
server. Verify player play/seek, ready and held states, required globals, keyboard focus,
student navigation stopping prior audio, zero new console errors, and no private path/URL/ID/auth
in DOM, response JSON, network payload, or console.

## Stop conditions

Return RED if the PAT cannot obtain a stable permitted source; the path requires HTML scraping,
credential forwarding, cookie persistence, software installation, `PATH` changes, or an audio
stream that cannot be scoped to session-owned workspace evidence. Return RED if a focused failure
requires a second result schema, bypasses existing review/write safeguards, or exposes protected
data.

## Execution result

- Traffic light: RED, awaiting the dummy-submission transport preflight.
- Commit: none.
- Changed files: this direct brief only.
- Commands/counts: `ffmpeg` and `ffprobe` capability check passed; Python 3.14 isolated
  `faster-whisper` install/import passed; no live Canvas read occurred.
- Deviations: none.
- Unresolved decision: the exact authorized Canvas media transport is intentionally unproved.
