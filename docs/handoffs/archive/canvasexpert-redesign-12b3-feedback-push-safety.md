# Toyota handoff 12b3: one safe Feedback Canvas-write path

Route both legacy Feedback UI and PowerGrader's migrated lane through one typed operation
adapter. The server reloads bundle/vault/result truth, validates contract and pseudonym
mapping, captures Canvas submission/comment baselines, freezes review, and applies only
approved targets. Browser previews are never authoritative. Missing comment history,
Canvas drift, repeated payload, partial failure, timeout/ambiguous response, and
re-identification mismatch block or receipt per the ledger contract. `ok:true` is forbidden
when any target failed. Applied targets are never resent.

Use exact owners from 12b0, new focused adapter tests, legacy route tests, and PG import
tests. Test cancel/no-write, drift/no-write, repeat/no-effect, partial/unresolved retry,
ambiguous Attention, and PII redaction. One commit; stop if either UI can bypass adapter.
