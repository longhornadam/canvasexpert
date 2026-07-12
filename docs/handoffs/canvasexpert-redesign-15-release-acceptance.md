# 15: Release acceptance

## Objective

Verify the operation ledger is complete and crash-safe, then declare the redesign
done. No browser runtime check. No live-fire matrix. No rendered verification.

## Acceptance criteria

1. **All focused adapter tests pass.** Every registered operation kind has a test
   file and it passes:
   - `test_quiz_operation.py` (11d1 + 11d2)
   - `test_assignment_operation.py` + `test_assignment_tier_operation.py`
   - `test_quick_assignment_operation.py`
   - `test_page_operation.py`
   - `test_rubric_operation.py`
   - `test_late_policy_operation.py`
   - `test_sweep_operation.py`
   - `test_extension_operation.py`
   - `test_curve_operation.py`
   - `test_roster_group_set_operation.py`
   - `test_roster_membership_operation.py`

2. **Full API test suite is green.** `py -m pytest api/tests` — all pass, at most
   one pre-existing skip.

3. **Restart recovery verified.** The recovery tests in `test_operation_ledger.py`
   pass: claimed/sent-unknown steps reconcile by exact IDs, operation status
   finalizes correctly, no duplicate sends after restart.

4. **`git diff --check` is clean.** No whitespace errors.

5. **No secrets, PII, or absolute paths in the diff.** Scan the full diff for
   token patterns, student names, or developer-specific paths.

6. **All registered kinds listed.** `registry.known_kinds()` returns every
   expected operation kind.

## What this is NOT

- No browser runtime verification (browser migration deferred)
- No live-fire Canvas matrix (not authorized)
- No rendered-app oracle check
- No SSE/event verification (polling only, 11d3)

## Commands

```powershell
py -m pytest api/tests
py -m pytest engine/tests
git diff --check
```

## Reference

`api/operation_ledger/registry.py::known_kinds` for the registered kind list.
`api/tests/test_operation_ledger.py` for the recovery test pattern.
