# Toyota handoff 11d1: QuizForge plan and whole-class operation

## Objective and boundary

Implement the no-network QuizForge plan subprocess and a registered, apply-capable
whole-class `content.quiz` adapter with exact quiz/item/assignment/module IDs. This is one
commit on `dev`. Do not migrate browser live controls or implement differentiated variants,
progress SSE, background/threaded apply, or legacy-route shutdown in this slice.

Read `docs/reference/quiz-operation-design.md`, `api/README.md`, `qf_pusher.py`, and the
operation protocol before editing. No live Canvas write is authorized.

## Pure plan contract

Refactor `api/qf_pusher.py` without changing legacy CLI behavior:

- Add `build_push_plan(path, settings)` that performs only local file parsing,
  `prepare_items`, `transform.build_item`, point distribution, and settings normalization.
- Return JSON-safe `{version:1,title,source_path,quiz_payload,items,assignment_settings,
  module}`. Each ordered item is `{index,source_item_id,source_type,payload}`.
- Quiz payload contains the exact `{"quiz": ...}` body currently POSTed, including current
  result-view and attempt/time/calculator defaults. Assignment settings are an allowlisted
  normalized dict; module contains requested ID/name only.
- Add `--plan-json` CLI mode. It accepts the existing path and `QF_PUSH_SETTINGS`, imports
  no Canvas client, performs no environment credential resolution/network call/state write,
  and writes exactly one JSON document to stdout. Errors go to stderr/nonzero exit.
- Legacy dry-run/live modes consume the same plan where mechanical, but retain their public
  CLI and output compatibility.

Add a bounded JSON subprocess helper in `api/webui/runner.py`: timeout, output-size cap,
nonzero/error handling, exact JSON-object parsing, and no credentials in argv/output.

## Quiz adapter

Add `api/operation_ledger/adapters/quiz.py::QuizAdapter`, kind `content.quiz`, and register/
export it. `build_payload` accepts exactly `{mode:"whole",path,settings}` in this slice,
runs the plan subprocess, validates version/schema/nonempty items, and freezes the plan.
Reject differentiated mode with a safe 400 until 11d2.

- `source_digest` covers the canonical plan and settings, excluding filesystem-only noise.
- `verify_targets` accepts only explicit active course IDs.
- Baseline lists Core assignments matching the normalized title with `new_quizzes=true`;
  before first write any match blocks. On retry, exact quiz IDs already checkpointed are
  allowed; unknown matches block.
- Review exposes course name, title, item count/types, total points, dates, publish/SIS,
  assignment group/module, attempts/time/result settings, and `mode=whole`; no full item
  bodies/path/course ID.

Execute one course target in this exact order:

1. `create_quiz:0` — `POST /api/quiz/v1/courses/{course_id}/quizzes`; write-ahead and
   checkpoint returned quiz/assignment ID and Canvas assignment URL.
2. `create_item:0:{index}` — ordered POSTs to the New Quiz items endpoint; checkpoint every
   returned item ID before the next item. Do not automatically retry a POST after any
   transport/429/5xx ambiguity.
3. `patch_assignment:0` when settings request Core assignment effects; PUT the exact
   assignment, checkpoint its ID, then GET and verify requested supported fields. A rejected
   requested effect is partial, never logged as success.
4. `create_module` once if a named module must be created/reused, then `attach_module:0`
   with exact returned module-item ID/content-ID verification.

Every existing step is verified by exact GET before reuse. Missing response ID or uncertain
transport is `sent_unknown`; definitive failure after a prior success is `partial`; retry
resumes the first unfinished step and duplicates nothing. Same-title matching never proves
success. Reconcile verifies quiz, every item, assignment patch, and module item exact IDs.
Reversal is unsupported.

Use `canvas_client` with explicit `/api/quiz/v1` versus `/api/v1` paths. Do not import the
token-loading CLI `canvas.py` in Web UI/adapter code.

## Files and tests

Expected files: `qf_pusher.py`, `webui/runner.py`, new adapter/registry exports, focused
tests, and only direct documentation corrections. Preserve legacy streaming/browser paths.

Tests must prove plan determinism/no network/no state write, malformed/oversized subprocess
output blocks, whole prepare/review, exact write order and IDs, each item ambiguity, partial,
retry, unknown same-title drift, exact reconcile, module behavior, PII-safe step receipts,
whole operation HTTP lifecycle, and unchanged legacy CLI-plan equivalence.

```powershell
py -m pytest api/tests/test_quiz_plan.py api/tests/test_quiz_operation.py api/tests/test_operation_routes.py api/tests/test_operation_ledger.py api/tests/test_route_contract.py
py -m pytest api/tests
git diff --check
```

Stop if plan mode imports Canvas/network code, transformed items cannot be represented
deterministically, the New Quiz create response lacks an exact usable ID, exact item GET is
unavailable, or a requested setting cannot be verified without a new product decision.
Reply with commit/files, plan schema evidence, object/write matrix, ambiguity/retry/reconcile
evidence, focused/full counts, no-state/no-live-write evidence, and leave the handoff active.
