# Toyota handoff: AI grading clarity and enforceable safety checkpoints

## Objective

Make the distinction between the two AI-assisted grading products unmistakable and replace skimmable safety prose with clear, truthful checkpoints. Preserve the existing local-only, pseudonymization, cost-guard, teacher-review, and Canvas-write safeguards.

## Dependencies

Complete handoffs 01–03 first, especially the shared `window.CE_WRITE_REVIEW.confirm` primitive from handoff 02.

## Product decision (do not merge the products)

Keep both workflows. They solve different jobs:

- **PowerGrader — Grade one assignment:** a keyboard-first review queue. It can be entirely local, use the teacher's AI chat, or make an OpenRouter draft-scoring run.
- **Score writing with AI — Batch feedback & import results:** prepares/uses feedback bundles, supports New Quizzes and external/manual tool results, and posts a reviewed batch.

Do **not** merge routes, session formats, vaults, packet formats, backend pipelines, or page implementations. Do **not** promise that either workflow is FERPA-safe or anonymous.

## Files to change

- `api/webui/templates/powergrader_setup.html`
- `api/webui/static/powergrader/setup_core.js`
- `api/webui/static/powergrader/setup_autoscore.js`
- `api/webui/static/powergrader_setup.css`
- `api/webui/templates/feedback_expert.html`
- `api/webui/static/feedback/guided_run.js`
- `api/webui/static/feedback/push.js`
- `api/webui/static/style.css` only for shared checkpoint styles
- `api/webui/README.md`

Do not alter `api/feedback_pipeline.py`, `api/powergrader/`, vault behavior, packet contents, OpenRouter request/response schemas, Canvas push routes, or scheduled auto-push policy in this handoff. This is sequencing, copy, and existing-client-call orchestration only.

## Required implementation

### 1. Give each page a clear, distinct opening

**PowerGrader**

- Change the opening heading/subhead to make `Grade one assignment` the primary message.
- Place a short `Choose how to grade` label above the three route cards.
- Rename the routes to: `Grade myself`, `Prepare for my AI chat`, and `Draft-score with OpenRouter`.
- Under each route, state the external effect in one plain sentence. The two AI routes must say that pseudonymization reduces exposure but can retain identifying context.
- Expand the current privacy/review details when either AI route is selected; it may stay collapsed for Grade myself.

**Feedback Expert**

- Rename the page heading to `Batch feedback & import results`.
- Make the first sentence explain it is for batch scoring, New Quiz/CSV workflows, and importing results from a teacher-chosen tool. It is not the assignment-by-assignment grading queue.
- Move persona configuration below the guided batch workflow. Persona setup is supporting configuration, not the job's first decision.
- Rename `Guided scoring` to `Prepare a feedback batch`.
- Retain the existing Push to Canvas review table and manual/CSV lane.

### 2. Split Feedback's prepare and send steps in the browser

`guided_run.js` currently prepares a SAFE bundle and, when a key is present, immediately asks for a native `confirm()` then starts the OpenRouter stream. Replace this with a visible staged interface, without changing the existing endpoints:

1. **Prepare SAFE batch** calls the existing `/api/feedback/run/prepare` endpoint and always stops after the response.
2. Render a status card with: assignment, student count, text/attachment caveats returned by the endpoint, model/cost estimate when available, and buttons to open the SAFE folder and proceed manually.
3. When OpenRouter is configured and the cost guard permits it, reveal a separate `Request draft scoring from OpenRouter…` button. It is disabled until the teacher checks this exact acknowledgement:

   `I understand that this sends the pseudonymized SAFE batch to OpenRouter. It may still contain identifying context.`

4. Clicking the enabled button uses `window.CE_WRITE_REVIEW.confirm`, adapted for an external paid AI request (not a Canvas write). Its target/details/warnings must include model, estimated cost (or explicitly `unavailable`), student count, and the exact data boundary above. The confirm label is `Send SAFE batch to OpenRouter`.
5. Only after this confirmation may the existing EventSource stream begin.

Never word the acknowledgement as `I reviewed the SAFE files`; the app cannot verify that claim. Manual users must instead be shown the exact honest instruction: `Open and review SAFE files before uploading them to any external AI tool.`

### 3. Add an explicit AI-disclosure checkpoint to PowerGrader

PowerGrader's AI routes create or send a SAFE packet during the Start action. It cannot truthfully require a prior review of a packet that does not exist yet.

For `Prepare for my AI chat` and `Draft-score with OpenRouter` only:

- Show a required, unchecked checkbox immediately above Start: `I understand that AI routes use a pseudonymized SAFE packet which may retain identifying context.`
- Disable `#pg-start-btn` until course, assignment, workspace, and this acknowledgement are present. Grade myself remains unaffected by this acknowledgement.
- For the OpenRouter route, preserve the existing server cost guard and existing post-start privacy pipeline. Do not replace it with client-only logic.
- For the AI-chat route, after the session is created, retain the existing SAFETY/PRIVATE guidance and add: `Review the SAFE files before uploading them to any external chat.`

The checkbox is a per-page transient UI state. Do not store it in localStorage, settings, a session artifact, or an audit record.

### 4. Keep Canvas-posting review separate

The external-AI confirmation is not a Canvas-write confirmation. Feedback's `Post selected to Canvas` continues to require the shared Canvas review dialog, with its current selected-row counts and warning language. Do not weaken it or combine the two prompts.

## Guardrails

- No statement may call a packet anonymous, guaranteed safe, FERPA-safe, or incapable of identity inference.
- Never show or log real student names, IDs, grades, submission content, token values, or full private file paths in status cards or dialogs.
- Do not change the scheduled auto-push opt-in/policy/idempotency behavior.
- Do not add telemetry, cloud storage, or external UI dependencies.

## Verification

Run:

```powershell
py -m pytest api/tests/test_feedback_safety.py api/tests/test_feedback_pipeline.py api/tests/test_feedback_vault.py api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_autoscore_queue.py api/tests/test_route_contract.py
```

Manual browser checks with a nonproduction/test course only:

1. PowerGrader: Grade myself starts without an AI acknowledgement; both AI routes cannot start until it is checked; changing route away from AI removes that prerequisite.
2. Feedback: Prepare produces no automatic OpenRouter stream. The OpenRouter send control remains disabled until acknowledgement and the normal cost guard permits it.
3. Cancel the external-AI review dialog; confirm no EventSource stream opens and the prepared SAFE batch remains available for manual use.
4. Confirm manual instructions say to review SAFE files before external upload and make no absolute privacy promise.
5. Confirm Feedback Canvas posting still requires the distinct Canvas-write review dialog and only posts checked preview rows.

## Acceptance criteria

- Teachers can identify the correct grading workflow before entering it.
- Preparing a Feedback SAFE batch never automatically sends it to OpenRouter.
- Every AI transmission is preceded by a clear, truthful, cancelable acknowledgement/confirmation.
- Existing automated safety, packet, queue, and route-contract tests pass without changes to sensitive backend behavior.

