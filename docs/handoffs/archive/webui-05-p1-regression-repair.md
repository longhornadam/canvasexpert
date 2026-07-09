# VSCode Toyota handoff: stop-the-line WebUI regression repair

## Purpose

Repair two confirmed P1 regressions introduced by commit `2b70abe` before continuing any WebUI redesign work. This is a narrow corrective change. Do not combine it with navigation, scope-component, or feature work.

## Evidence (already independently reproduced)

1. The rendered Feedback DOM has `#push-section` inside `#persona-card`. The cause is a missing closing `</section>` after the persona form.
2. `syncStartEnabled()` can enable PowerGrader Start after a course and assignment are selected even when no workspace is configured. The template initially disables Start for that case, but the client helper overwrites it.

## Files to change

- `api/webui/templates/feedback_expert.html`
- `api/webui/templates/powergrader_setup.html`
- `api/webui/static/powergrader/setup_core.js`
- `api/webui/README.md` only if its implementation notes need an accurate workspace-gating statement.
- **New test:** `api/tests/test_webui_template_contracts.py`

Do not modify Canvas routes, PowerGrader session code, feedback pipeline/vault code, `LLM_Modules/`, or any source/workspace/student data.

## Required change A — Feedback template structure

In `feedback_expert.html`, add the missing `</section>` immediately after the `#persona-form` closing `</form>`, before the `Push to Canvas` section begins.

The resulting structure must be siblings under the page main content:

```html
<section id="persona-card"> ... </section>
<section id="push-section"> ... </section>
```

Do not rely on browser error recovery. Do not move Push to Canvas, change its IDs, or change any form controls.

## Required change B — preserve the workspace prerequisite

Add a server-rendered, non-secret boolean to `window.POWERGRADER_SETUP_CONFIG` in `powergrader_setup.html`:

```js
hasWorkspace: {{ has_workspace | tojson }}
```

In `setup_core.js`, make `syncStartEnabled()` use that value. Its enable condition must be:

```text
hasWorkspace AND selected course AND selected assignment AND (non-AI route OR AI acknowledgement checked)
```

Requirements:

- When no workspace exists, Start remains disabled after any course/assignment/mode/acknowledgement change.
- Grade myself remains startable without the AI acknowledgement when a workspace exists.
- Both AI routes still require the acknowledgement when a workspace exists.
- Do not infer workspace readiness from the button's current disabled state.
- Do not change the existing server-side validation; this is an additional UI guard.

## Required regression test

Create `api/tests/test_webui_template_contracts.py` with small, deterministic source-contract tests. It must:

1. Read `feedback_expert.html` and assert that the first `</section>` after `id="persona-card"` occurs before `id="push-section"`.
2. Read `powergrader_setup.html` and assert the setup config includes `hasWorkspace` sourced from `has_workspace`.
3. Read `setup_core.js` and assert `syncStartEnabled` uses the configured workspace flag as part of the enable condition.

These tests intentionally guard the exact failure modes. Keep them narrow; they must not contain student data or depend on a live Canvas token.

## Verification — required, not optional

Run:

```powershell
py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_feedback_safety.py api/tests/test_route_contract.py
```

Then launch the local app with `cd api; py qf_ui.py` and perform these read-only checks:

1. Open `/feedback-expert`. In browser developer DOM inspection, verify `#persona-card` and `#push-section` share the same parent; visually, Push to Canvas must not be inset inside the persona card.
2. Run the app with an intentionally unconfigured workspace (use the existing normal onboarding/config mechanism; do not edit source or secrets). On `/powergrader`, select a course and assignment. Start must remain disabled for every route.
3. With a configured workspace, verify Grade myself enables after course + assignment; each AI route remains disabled until acknowledgement is checked.

Do not start a grading session, send an AI request, or post to Canvas while verifying this handoff.

## Completion evidence required in the implementer reply

The implementer must report:

- exact changed files;
- the pytest command and final pass count;
- the three manual outcomes above;
- confirmation that no Canvas/AI write was performed.

Do not archive this handoff and do not write “done” until all four evidence items are present.

