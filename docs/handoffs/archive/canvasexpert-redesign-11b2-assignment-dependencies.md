# Toyota handoff 11b2: assignment files, printable, and module dependencies

## Objective

Extend accepted `content.assignment` with source uploads/printable attachment and module
placement only. Rubric association remains excluded until 11c1 is accepted.

Use the existing upload, printable, and module helpers exposed as pure adapter calls;
edit `assignment.py`, `push_service.py`, `static/push/{assignment,delivery}.js`, and
focused assignment/printable tests. Review lists each dependency. Per target execute
upload -> assignment update/attachment -> module item, blocking downstream effects only.
Each created object has its own target key and returned ID. Ambiguous results block;
filename/title similarity is not proof. Retry never duplicates a proven upload/module item.

Test missing/invalid files, upload partial, module drift, ambiguous response, exact IDs,
unresolved-only retry, and core-only parity. Run assignment operation, push-service,
printable-attach, route, JS, and diff checks. Stop if an existing helper combines rubric
or scheduled behavior inseparably. One commit with dependency-order evidence.

Accepted by Ferrari on 2026-07-11 after integration repair `a2d6617`. Rubric association
and differentiated/tier behavior remain excluded.
