# Toyota handoff 12a: PowerGrader Workbench and grading Instrument

## Objective

Integrate existing PowerGrader sessions into Work/Continue/Attention and migrate approved
manual grade posts to registered operation kind `grade.powergrader`, while preserving the
keyboard-first Instrument and all privacy/AI contracts.

## Files

- `api/powergrader/session_store.py` summary adapter only
- New `api/operation_ledger/adapters/powergrader_grade.py`
- Adapter registry
- `api/webui/routes/powergrader.py`
- `api/webui/templates/powergrader_setup.html`
- `api/webui/templates/powergrader_queue.html`
- `api/webui/static/powergrader_queue.css`
- `api/webui/static/powergrader/queue_core.js`
- `api/webui/static/powergrader/queue_review.js`
- Work registry adapter/tests
- New `api/tests/test_powergrader_grade_operation.py`
- Existing PowerGrader focused suites/module map

## Behavior

Both PowerGrader templates extend `workbench_base.html`; use its extension blocks and do
not reload Workbench CSS.

PowerGrader setup is a Workbench job start. Existing sessions appear in Continue; late
catch-up, import, failed/partial autoscore, and held decisions appear in Attention without
copying session authority. Queue is the Instrument state.

Save/approve remains local PRIVATE session mutation. “Post one/all” prepares a grade
operation; shared immutable review/apply occurs through the ledger. Keyboard `b` opens
review and cannot apply directly. AI draft fields remain visually distinct from edited /
approved teacher values. Existing scheduled per-job auto-push remains its narrow separate
policy path and produces compatible receipts without broadening eligibility.

Adapter freezes approved/not-posted students, score/comment/lateness payload digests, and
Canvas drift baselines. Apply/retry/idempotency use slice 04 safety rules and per-user
outcomes. No student detail appears in registry, list API, activity, or console evidence.

## Verification

```powershell
node --check api/webui/static/powergrader/queue_core.js
node --check api/webui/static/powergrader/queue_review.js
py -m pytest api/tests/test_powergrader_grade_operation.py api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_import_results.py api/tests/test_powergrader_late_catchup.py api/tests/test_powergrader_autoscore_queue.py api/tests/test_powergrader_autopush_policy.py api/tests/test_powergrader_autopush_executor.py api/tests/test_feedback_safety.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py
git diff --check
```

Runtime setup+queue, resume, packet,
OpenRouter-disabled path, import, approval, one/bulk review, keyboard, partial fixture,
late catch-up, dark/light, 1920/2560, zero console errors. No real Canvas/AI call.

Stop if existing sessions require migration, if keyboard can bypass review, or if the
scheduled-auto-push exception would be broadened.

## Required implementer reply

One commit; report hash/files, every command/pass count, job/session parity, keyboard and
review evidence, partial/idempotency results, privacy redaction, console count, and no real
Canvas/AI call or unrelated staging.
