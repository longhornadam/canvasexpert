# Toyota handoff 13b2: due-date extension operation adapter

## Objective

Migrate individual/bulk due-date extensions to kind `gradebook.extension` with current
Canvas/roster revalidation and truthful reversal.

## Files

- New `api/operation_ledger/adapters/extension.py`
- `api/webui/routes/gradebook_extensions.py`
- Existing due-date calculation helper owner
- `api/webui/static/gradebook/extensions.js`
- New `api/tests/test_extension_operation.py`
- Existing gradebook/schooldays/roster-config tests

## Contract

Prepare freezes assignment, explicit student targets, prior overrides/dates, requested
school-day/calendar logic, and proposed dates. Review/apply reload current assignment,
overrides, calendars, and extra-time state; drift invalidates review. Per-student payloads
remain PRIVATE. Repeat target state is idempotent; retry unresolved students only.
Reversal is `restore_snapshot` only when each prior override/date was captured and current
state still equals the applied value.

For each target inspect every assignment override. With none, create one student-specific
override for that student only. With exactly one candidate whose only student is the
target, update it. If a candidate is shared, section/group scoped, overlapping, or more
than one applies, block `ambiguous_override`; never mutate it or create an overlap. Do not
group newly created student overrides. Reversal deletes an override created here or
restores the captured exclusive snapshot only when Canvas still equals the applied value.
Unrelated students and overrides are never touched.

Test none/exclusive/shared/multiple/section/group/overlap, single/bulk, extra time,
deleted objects, date/calendar drift, partial, repeat, retry, both reversal forms,
unaffected-student proof, and redaction. Live-fire requires disposable targets.

## Verification and handoff reply

```powershell
node --check api/webui/static/gradebook/extensions.js
py -m pytest api/tests/test_extension_operation.py api/tests/test_gradebook_routes.py api/tests/test_schooldays.py api/tests/test_roster_config.py api/tests/test_route_contract.py
git diff --check
```

Stop if prior overrides cannot be captured or current-state drift cannot block. One commit;
report hash/files, commands/pass counts, single/bulk/drift/partial/retry/reversal evidence,
redaction, runtime console count, and live-fire authorization state.
