# VSCode Toyota handoff: finish AI-grading safety behavior

## Purpose

Finish the partially implemented AI-grading slice after the shared review primitive exists. Preserve the good changes already present: Feedback prepares before it sends; PowerGrader has distinct AI route language; the privacy claims are honest.

## Dependencies

Complete `webui-05-p1-regression-repair.md`, `webui-06-shared-scope-review-completion.md`, and `webui-07-task-ia-completion.md` first.

## Files to change

- `api/webui/static/feedback/guided_run.js`
- `api/webui/templates/feedback_expert.html`
- `api/webui/static/powergrader/setup_core.js`
- `api/webui/templates/powergrader_setup.html`
- `api/webui/static/powergrader_setup.css`
- `api/tests/test_webui_template_contracts.py`

Do not change feedback pipeline endpoints, PowerGrader session behavior, packet format, vault behavior, OpenRouter schemas, Canvas posting, scheduled auto-push policy, or any authoring contract.

## Required implementation

### Feedback OpenRouter review

Delete the bespoke `startOpenRouterStream` modal implementation. Use `window.CE_WRITE_REVIEW.confirm` for the external-AI confirmation, with an appropriate non-Canvas title and the existing model, estimated cost/unavailable status, student count, SAFE data boundary, and honest identifying-context warning.

The acknowledgement must remain required and must read exactly:

`I understand that this sends the pseudonymized SAFE batch to OpenRouter. It may still contain identifying context.`

Prepare must still stop before streaming. Cancel must not open an EventSource. A successful/failed/cancelled request must leave the prepared SAFE batch available for manual use.

Remove unused state and controls: if `_orStreamActive` or `#gf-or-status` remain unused after implementation, delete them.

### PowerGrader disclosure behavior

When either AI route is selected:

- programmatically expand `#pg-safety-popout` (`open = true`);
- retain the required acknowledgement gating from handoff 05;
- preserve Grade myself as local/no-acknowledgement;
- do not word any checkbox as proof that the teacher reviewed a packet that does not yet exist.

### Test coverage

Extend `test_webui_template_contracts.py` to assert:

- Feedback uses `CE_WRITE_REVIEW.confirm` and no longer creates `ce-review-backdrop` directly in `guided_run.js`;
- the exact acknowledgement text remains present;
- PowerGrader's safety details have the stable `pg-safety-popout` ID and setup code opens it for AI routes.

## Verification — required, not optional

Run:

```powershell
py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_feedback_safety.py api/tests/test_feedback_pipeline.py api/tests/test_feedback_vault.py api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_autoscore_queue.py api/tests/test_route_contract.py
```

Manual local browser checks with no external send or Canvas write:

1. Prepare a SAFE batch. Confirm no EventSource starts automatically.
2. Acknowledge, open the external-AI review, then cancel. Confirm the SAFE batch remains available and no stream starts.
3. Switch among all three PowerGrader routes. The privacy details open for AI routes; only AI routes require acknowledgement.
4. Tab through the external-AI review: focus stays in the shared dialog and Escape cancels.

## Completion evidence required

Report the test pass count, source-contract assertions, and all four manual outcomes. Do not archive this handoff or report “all slices done” until the evidence is provided.

