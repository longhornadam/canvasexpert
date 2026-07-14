# Feedback Tools Module Map

Purpose: give future agents a compact map for the pseudonymized feedback/scoring
surface without reading privacy-sensitive workflow code first.

As of 2026-07-08, feedback tools have solid privacy guardrails. The route layer and
pipeline layer are split into focused modules, with compatibility facades kept for
older imports. Refactor only with focused tests and privacy review.

## Ownership

- Main page template: `api/webui/templates/feedback_expert.html`
- Browser bootstrap/shared helpers: `api/webui/static/feedback/core.js`
- Folder open actions: `api/webui/static/feedback/folders.js`
- Persona library + save flow: `api/webui/static/feedback/personas.js`
- Guided scoring prepare/stream: `api/webui/static/feedback/guided_run.js`
- Inbox process + re-identify: `api/webui/static/feedback/manual.js`
- OpenRouter config + CSV lane: `api/webui/static/feedback/openrouter.js`
- Push preview/apply review table: `api/webui/static/feedback/push.js`
- Name/vault page template: `api/webui/templates/name_manager.html`
- Route registration owner: `api/webui/routes/feedback.py`
- Manual workflow routes: `api/webui/routes/feedback_manual.py`
- Persona/pattern routes: `api/webui/routes/feedback_library.py`
- Guided scoring routes: `api/webui/routes/feedback_run.py`
- Canvas push routes: `api/webui/routes/feedback_push.py`
- Shared route helpers: `api/webui/routes/feedback_common.py`
- Pipeline facade: `api/feedback_pipeline.py`
- Contract helpers: `api/feedback_contract.py`
- Artifact helpers: `api/feedback_artifacts.py`
- Result helpers: `api/feedback_results.py`
- Scrubber: `api/feedback_scrub.py`
- Safety scanner: `api/feedback_safety.py`
- Local vault: `api/feedback_vault.py`
- Scoring contract: `docs/contracts/feedback-scoring-contract.md`

## Current Size Snapshot

- `api/webui/templates/feedback_expert.html` - 267 lines
- `api/webui/static/feedback/core.js` - 114 lines
- `api/webui/static/feedback/folders.js` - 13 lines
- `api/webui/static/feedback/personas.js` - 57 lines
- `api/webui/static/feedback/guided_run.js` - 204 lines
- `api/webui/static/feedback/manual.js` - 21 lines
- `api/webui/static/feedback/openrouter.js` - 139 lines
- `api/webui/static/feedback/push.js` - 176 lines
- `api/feedback_artifacts.py` - 425 lines
- `api/webui/templates/name_manager.html` - 441 lines
- `api/feedback_vault.py` - 297 lines
- `api/webui/routes/feedback_run.py` - 223 lines
- `api/feedback_results.py` - 196 lines
- `api/feedback_scrub.py` - 191 lines
- `api/webui/routes/feedback_manual.py` - 155 lines
- `api/webui/routes/feedback_push.py` - 121 lines
- `api/feedback_pipeline.py` - 84 lines
- `api/feedback_contract.py` - 98 lines
- `api/feedback_safety.py` - 75 lines
- `api/webui/routes/feedback_common.py` - 72 lines
- `api/webui/routes/feedback_library.py` - 45 lines
- `api/webui/routes/feedback.py` - 19 lines

## Route Routing

`routes/feedback.py` only registers the split routers and re-exports
`_push_payload` for older tests/imports.

Route module ownership:

- `feedback_manual.py`
  - `/persona`
  - `/process-inbox`
  - `/reidentify`
  - `/openrouter-config`
  - `/status`
  - `/score-openrouter`
- `feedback_library.py`
  - `/personas`
  - `/personas/custom`
  - `/patterns`
- `feedback_run.py`
  - `/run/prepare`
  - `/run/stream`
  - code-file attachment enrichment for guided scoring
- `feedback_push.py`
  - `/push/preview`
  - `/push/apply`
  - current Canvas score lookup, SAFE bundle lookup, and Canvas PUT payloads
- `feedback_common.py`
  - canonical `_System/Identity Vault` resolution, rubric text loading,
    content-free audit receipts, bundle discovery, and budget error wording

## Pipeline Routing

`feedback_pipeline.py` now only owns the compatibility facade and re-exports.

The split implementation lives in:

- pseudonymizing parsed quiz files and Canvas submissions
- writing SAFE and PRIVATE artifacts
- prompt/contract text generation
- deep scrub and post-scrub verification
- AI result parsing and validation against the scoring contract
- feedback normalization and persona signoff cleanup
- re-identification and CSV output
- inbox and FromLLM directory processors

- `feedback_artifacts.py` - pseudonymize, bundle shaping, SAFE/PRIVATE file writing,
  inbox processing, and directory re-identification
- `feedback_contract.py` - scoring prompt and contract text
- `feedback_results.py` - parse, validate, normalize, re-identify, CSV
- `feedback_pipeline.py` - compatibility facade for legacy imports

## Browser Routing

`feedback_expert.html` is now mostly markup plus script includes.

Browser load order:

1. `static/feedback/core.js`
2. `static/feedback/folders.js`
3. `static/feedback/personas.js`
4. `static/feedback/guided_run.js`
5. `static/feedback/manual.js`
6. `static/feedback/openrouter.js`
7. `static/feedback/push.js`

Shared namespace seam: `window.CE_FEEDBACK`

Keep the browser split in plain scripts under `api/webui/static/feedback/`.
Do not add a framework or build step.

## First Places To Look By Symptom

- shared escape/status/folder bootstrap: `static/feedback/core.js`
- SAFE / PRIVATE / Inbox / FromLLM / ToEnter button wiring:
  `static/feedback/folders.js`
- persona dropdown or save behavior: `static/feedback/personas.js`
- SAFE/PRIVATE artifact shape: `feedback_artifacts.py`, `feedback_pipeline.py`,
  `feedback_scrub.py`,
  `feedback_safety.py`
- pseudonym/name mismatch: `feedback_vault.py`, `feedback_artifacts.py`
- guided scoring errors: `static/feedback/guided_run.js`, `routes/feedback_run.py`,
  `feedback_pipeline.py`, `api/openrouter_client.py`
- inbox / re-identify / manual CSV lane: `static/feedback/manual.js`,
  `routes/feedback_manual.py`, `feedback_pipeline.py`
- OpenRouter config / bundle scoring lane: `static/feedback/openrouter.js`,
  `routes/feedback_manual.py`, `api/openrouter_client.py`
- push preview/apply errors: `static/feedback/push.js`, `routes/feedback_push.py`,
  `docs/contracts/feedback-scoring-contract.md`
- persona/pattern issues: `routes/feedback_library.py`, `api/webui/config/feedback.py`
- Name Manager behavior: `name_manager.html`, `feedback_vault.py`,
  `feedback_scrub.py`

## Guardrails

- SAFE files are pseudonymized, not guaranteed anonymous. Keep teacher review wording
  honest.
- PRIVATE files, vault data, real names, IDs, submissions, grades, and comments must
  never be committed or printed into fixtures/logs.
- AI suggestions are drafts until teacher review and explicit push.
- Preserve the Feedback Scoring Contract unless a migration is explicitly planned.
