# Ferrari handoff 11c0: prove the RubricForge live-write path

## Objective

Documentation-only discovery. Reconcile `api/README.md` with `_push_rubricforge` and all
routes/callers/tests before any rubric adapter is authorized.

Use `rg` and the route/service/module maps to document in
`docs/reference/rubric-live-path.md`: every UI entry, route, parser, Canvas method,
association behavior, return shape, and test; exact load/call order; whether live create
actually works; and discrepancies. Do not change runtime code. If no supported live path
exists, state that the product is prepare-only and 11c1 remains blocked until Ferrari
defines new behavior. Update misleading canonical docs only when evidence is conclusive.

```powershell
rg -n "RubricForge|rubricforge|_push_rubric|create_rubric|association" api docs LLM_Modules
py -m pytest api/tests/test_rf.py api/tests/test_route_contract.py
git diff --check
```

One documentation commit. Reply with hash, call graph, discrepancy table, current
capability verdict, and exact proposed 11c1 insertion points. Stop on contradictory paths.

Accepted by Ferrari on 2026-07-11. Its discovery was consumed by 11c1 and corrected by
the 11r integration acceptance repair.
