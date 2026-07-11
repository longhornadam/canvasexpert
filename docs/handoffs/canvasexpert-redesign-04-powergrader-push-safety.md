# Toyota handoff 04: two-step manual PowerGrader push safety

## Objective

Make every manual PowerGrader push a frozen server review followed by a drift-checked
apply. This is a safety repair before the universal Work rail, not the ledger migration.

## Files

- `api/powergrader/session_actions.py`
- `api/powergrader/session_store.py`
- `api/webui/routes/powergrader.py` (reuse its `canvas_get` dependency; do not add a
  second Canvas client)
- `api/webui/static/powergrader/queue_review.js`
- New `api/tests/test_powergrader_manual_push.py`
- Template/route contract tests and `docs/reference/powergrader-module-map.md`

## Review endpoint and frozen state

Add `POST /api/powergrader/session/{session_id}/push-review`, accepting string user IDs.
The server selects only present, approved, unposted rows having score or feedback. For
each selected submission, perform a bounded GET with
`include[]=submission_comments` and capture score, grade, graded_at, updated_at, and
latest comment ID/count/created_at.

Persist one PRIVATE `pending_push_review` inside the session: opaque random token,
expiry 15 minutes, ordered IDs, normalized payload digests, Canvas baselines, and
overall digest. Never return names or provider exceptions. Any `save_grade`, approval,
feedback, score, lateness, or selection mutation invalidates it.

## Apply endpoint

The existing push POST now requires the review token and exact ordered IDs. Missing,
expired, invalidated, or mismatched review rejects before PUT. It refetches the selected
submissions and compares the captured baseline. Feedback writes require comments to be
available and unchanged; if comment retrieval is absent or ambiguous, block them.
Score-only writes may compare score/grade/graded_at/updated_at. Drift returns
`drift_detected`; direct apply without review is rejected.

Persist a target idempotency digest from session/user/approved payload. A confirmed
successful digest cannot call Canvas again. Return per-user `pushed|failed|blocked`
outcomes with stable codes. Update only confirmed pushed rows; partial success must not
mark all approved rows posted. PRIVATE diagnostics stay in the session log.

## Browser behavior

`pushOne`, `bulkPush`, and keyboard `b` call push-review, render its server summary
through `CE_WRITE_REVIEW.confirm` with Cancel initially focused, then submit the token
to apply. Any mutation or expired review restarts review. Buttons re-enable on every
success/partial/failure/cancel path.

## Verification

Test unauthorized row states, empty/invalid IDs, review expiry/invalidation, direct
apply rejection, score drift, comment drift/unavailability, zero score, comment-only,
repeat apply, partial Canvas failure, redaction, and exact session mutation.

```powershell
node --check api/webui/static/powergrader/queue_review.js
py -m pytest api/tests/test_powergrader_manual_push.py api/tests/test_powergrader_autopush_policy.py api/tests/test_powergrader_autopush_executor.py api/tests/test_powergrader_import_results.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py
git diff --check
```

Render a fictional PRIVATE session: one/bulk/`b`, Cancel focus, mutation invalidation,
partial UI, zero console errors. No real grade write in ordinary acceptance. Stop if
comments/baselines cannot be retrieved or session persistence cannot invalidate review.
One commit; reply with hash, tests, endpoint traces with opaque IDs, and rendered evidence.
