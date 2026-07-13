# Execution brief: decompose the content-operation adapter monoliths

Status: **ready for implementation**

Risk: **high**

Executor: **external VS Code agent**

## Outcome

Quiz and Assignment content operations retain exactly the same prepare, review, apply,
reconcile, retry, receipt, and Canvas-write behavior, but their 1,892- and 1,446-line
adapter files become thin lifecycle facades over focused execution modules. Proven
step/result and Canvas-assignment module-placement duplication is removed across the
five content adapters without introducing a new framework.

This is a behavior-frozen structural refactor. Its value is safer navigation and future
maintenance of high-risk Canvas-write code, not a new teacher feature.

## Locked decisions

- `QuizAdapter`, `AssignmentAdapter`, `PageAdapter`, `RubricAdapter`, and
  `QuickAssignmentAdapter` keep their current registered kinds and adapter protocol.
- Operation payloads, source/review digests, persisted records, target/step keys and
  ordering, Canvas methods/paths/payloads, checkpoint timing, returned result shapes,
  error codes, private diagnostics, and receipt behavior are frozen.
- `quiz.py` and `assignment.py` become facade/prepare-review owners. Whole and
  differentiated/tiered execution move behind them; callers and the registry continue
  importing the same adapter classes from the same paths.
- Use composition and module functions. Do not add a base adapter, mixin hierarchy,
  dependency container, result class, plugin registry, generic executor, or new durable
  interface.
- Extract only the content-adapter helpers whose semantics are already identical.
  Gradebook and roster adapters are deliberately excluded even where names look
  similar.
- Canvas Assignment-type module placement is one implementation shared by whole/tiered
  Assignment and whole/differentiated Quiz flows. Page module placement remains in
  `page.py` because its Canvas item type and identity rules differ.
- Preserve the existing monkeypatch seams on the facade modules for
  `resolve_assignment_groups`, `canvas_client`, `config`, and `_autoscore_queue` by
  passing callable dependencies from the facade when needed. Do not force the tests to
  know every leaf-module import solely to make the extraction easier.
- Preserve `assignment.py::_validate_printable_pdf` and `_upload_course_file` as usable
  private compatibility imports for the focused printable tests, whether they remain
  defined there or are explicitly re-exported from a leaf module.
- No live Canvas request is permitted during verification.
- An evidenced GREEN is trusted. The senior will inspect the summary and narrow risk
  seams only and will not rerun successful verification.

## Scope

Create these focused modules under `api/operation_ledger/adapters/`:

- `adapter_support.py` — content-adapter step/result primitives only.
- `module_placement.py` — shared find/create-module and attach-Canvas-Assignment-item
  behavior for Assignment and Quiz operations.
- `assignment_whole.py` — whole-class Assignment execute/reconcile coordination.
- `assignment_tiered.py` — tiered Assignment execute/reconcile coordination and its
  tier-only helpers.
- `quiz_steps.py` — write-ahead phase helpers shared by whole and differentiated Quiz
  execution.
- `quiz_whole.py` — whole-class Quiz execute/reconcile coordination.
- `quiz_differentiated.py` — differentiated Quiz coordination, reconciliation,
  group/extra-time handling, and variant failure-state policy.

Modify:

- `api/operation_ledger/adapters/assignment.py`
- `api/operation_ledger/adapters/quiz.py`
- `api/operation_ledger/adapters/page.py`
- `api/operation_ledger/adapters/rubric.py`
- `api/operation_ledger/adapters/quick_assignment.py`
- Directly affected tests only where imports/patch seams require it.
- `AGENTS.md` and a new concise
  `docs/reference/operation-ledger-module-map.md` for current ownership/routing.

At GREEN closure, move the completed
`docs/handoffs/course-expert-canonical-surface-retirement.md` and this brief to
`docs/handoffs/archive/` in the same implementation commit. If the result is YELLOW or
RED, leave this brief active at its current path.

## Out of scope

- No teacher-visible behavior, routes, browser scripts/templates, CLI behavior, Canvas
  API behavior, authoring contract, or operation-ledger durable contract change.
- No persistence/schema/version migration and no changes to `models.py`, `storage.py`,
  `executor.py`, claims, recovery, batches, operations, receipts, or route handlers.
- Do not alter gradebook/roster adapters (`late_policy`, `sweep`, `curve`, `extension`,
  `roster_group_set`, `roster_membership`) or extract a universal adapter abstraction.
- Do not change Page's module-item implementation or try to generalize Page and
  Assignment module placement together.
- Do not split or prune the large operation test files in this handoff. Update patch
  paths only when a preserved facade seam cannot reasonably cover the moved owner.
- Do not add source-text architecture tests, snapshot tests of implementation text,
  compatibility wrappers for unused private helpers, or a new test-fixture framework.
- Do not refactor operation-ledger storage/executor code, autoscore policy, group
  resolution, QuizForge planning, Canvas clients, or unrelated monoliths.
- Do not create another planning document or retain parallel active handoffs.

## Reference pattern and routing

- Durable invariants: `docs/contracts/operation-ledger-contract.md`
- Current adapter protocol/rationale:
  `docs/reference/operation-ledger-design.md::3. Adapter interface`
- Registry/public import boundary:
  `api/operation_ledger/__init__.py`,
  `api/operation_ledger/adapters/__init__.py`
- Facade owners:
  `api/operation_ledger/adapters/assignment.py::AssignmentAdapter`,
  `api/operation_ledger/adapters/quiz.py::QuizAdapter`
- Existing shared group resolver:
  `api/operation_ledger/adapters/assignment_groups.py`
- Existing execution context/checkpoint contract:
  `api/operation_ledger/executor.py`
- Required behavior suites:
  `api/tests/test_assignment_operation.py`,
  `api/tests/test_assignment_tier_operation.py`,
  `api/tests/test_quiz_operation.py`,
  `api/tests/test_quiz_tier_operation.py`,
  `api/tests/test_page_operation.py`,
  `api/tests/test_quick_assignment_operation.py`,
  `api/tests/test_rubric_operation.py`,
  `api/tests/test_printable_attach.py`
- Read project-local `TOOLS.md` before broad manual inspection. `repo-indexer` and
  `change-risk-summarizer` are currently planned rather than callable; use `rg`, AST,
  and `tools/size_report.py` rather than rereading unrelated files.

Do not use archived handoffs as implementation authority.

## Implementation requirements

1. **Add a deliberately small content-adapter support module.** It may own the existing
   semantics of:

   - fixed-order step projection for callers that supply an explicit order;
   - find-new/prepend/ensure/replace step helpers using `models.new_step`;
   - module ID recovery from create/attach steps;
   - outbound-marker detection;
   - scalar-to-list normalization;
   - uncertain transport-error classification;
   - the full standard adapter result dictionary.

   Assignment and Quiz retain their mode-specific custom step ordering. Do not move
   adapter protocol methods such as `verify_targets`, `target_key`, `idempotency_key`,
   `retry_selector`, or `reversal_descriptor` into a base class.

2. **Extract one shared Assignment-type module-placement path.** Preserve the exact
   lookup, ambiguity, create, write-ahead, checkpoint, exact-ID verification, module
   item payload, returned IDs, state, and error-code behavior of the current Assignment
   and Quiz implementations. Its explicit inputs must include course/content identity,
   title, module name, mutable steps, execution context, attach step key, and the outer
   deterministic failure state where modes differ. It must not know about adapter
   classes or persisted operation records.

3. **Make `AssignmentAdapter` a lifecycle facade.** Keep prepare/build, digest, target,
   baseline, drift, frozen review, retry, reversal, and the current patchable dependency
   names in `assignment.py`. Delegate whole/tiered execute and reconcile to their leaf
   modules. Pass the facade's `resolve_assignment_groups`, `_autoscore_queue`, and any
   required assignment-group/autoscore callbacks explicitly so existing tests retain
   meaningful patch points and leaf modules do not import the facade.

4. **Decompose Assignment execution by durable phases.** `assignment_whole.py` owns the
   whole-class create/printable/module/autoscore flow. `assignment_tiered.py` owns tier
   assignment creation, exact override creation, optional module placement, optional
   autoscore scheduling, and exact-ID reconciliation. The tier coordinator should read
   like the ordered step model; extract phase helpers when needed so no new function
   exceeds 180 lines.

5. **Make `QuizAdapter` a lifecycle facade.** Keep plan construction, digest, target,
   baseline, drift, frozen review, retry, reversal, and the patchable
   `resolve_assignment_groups` name in `quiz.py`. Delegate whole/differentiated execute
   and reconcile to leaf modules and pass the resolver explicitly.

6. **Decompose Quiz execution at its existing write-ahead boundaries.** `quiz_steps.py`
   owns focused phase functions for quiz creation/exact-ID verification, assignment
   restriction, overrides, item creation, assignment patch/verification, and shared
   module placement. `quiz_whole.py` and `quiz_differentiated.py` remain coordinators.
   The differentiated coordinator must no longer be a 545-line procedure; keep it at
   or below 180 lines and keep each phase helper at or below 180 lines. Use ordinary
   dictionaries, tuples, mutation of the existing steps list, and `None`/early-result
   returns—do not invent a second result protocol.

7. **Preserve every dangerous seam exactly.** The refactor must not change:

   - the order of `context.before_send`, Canvas request, and
     `context.checkpoint_step`;
   - any step key, step ordering, outbound digest input, Canvas request payload, or
     exact-ID verification request;
   - `failed` versus `partial` versus `sent_unknown` classification;
   - no-resend behavior after an outbound marker or uncertain response;
   - safe group snapshots versus transient student IDs;
   - extra-time bucket behavior;
   - module/override/item correlation IDs;
   - autoscore job IDs, policy, idempotent upsert, or partial-failure behavior;
   - printable path validation and upload behavior;
   - returned adapter result keys, values, or private diagnostic minimization.

8. **Keep dependencies acyclic and one-directional.** Required direction:

   ```text
   assignment.py -> assignment_whole.py / assignment_tiered.py
                                      -> module_placement.py / adapter_support.py

   quiz.py -> quiz_whole.py / quiz_differentiated.py
                         -> quiz_steps.py
                         -> module_placement.py / adapter_support.py
   ```

   Leaf modules may import shared Canvas/config/model modules, but they must never
   import `AssignmentAdapter`, `QuizAdapter`, or their facade modules.

9. **Meet explicit monolith acceptance bounds.** After the refactor:

   - `assignment.py` and `quiz.py` are each at or below 550 physical lines;
   - no newly created module exceeds 500 physical lines;
   - no newly created function exceeds 180 physical lines;
   - `page.py`, `rubric.py`, and `quick_assignment.py` consume shared helpers and do
     not grow;
   - total production lines under `api/operation_ledger/adapters/` do not increase.

   These are structural acceptance bounds, not a request to compress readable code or
   delete safety handling. Return YELLOW with the exact reason if a bound cannot be met
   without semantic redesign.

10. **Document current ownership concisely.** Add
    `docs/reference/operation-ledger-module-map.md` with facade/execution/support/test
    routing, safety boundaries, and current post-refactor size snapshot. Add one link
    from `AGENTS.md`; do not duplicate the durable contract or write a refactor diary.

11. **Self-review before verification.** Compare moved code against the pre-refactor
    behavior by durable step phase, not just by test names. Record before/after adapter
    LOC, the largest remaining function, any changed test patch paths, and net adapter
    production LOC in the execution result.

## Verification

Focused high-risk matrix:

```powershell
py -m pytest api/tests/test_operation_ledger.py api/tests/test_operation_routes.py api/tests/test_assignment_operation.py api/tests/test_assignment_tier_operation.py api/tests/test_printable_attach.py api/tests/test_quiz_operation.py api/tests/test_quiz_tier_operation.py api/tests/test_page_operation.py api/tests/test_quick_assignment_operation.py api/tests/test_rubric_operation.py
```

Completion boundary for the cross-cutting/high-risk API refactor:

```powershell
py -m pytest api/tests
py tools/size_report.py
git diff --check
```

No rendered browser check is required because routes, templates, shared browser files,
and visible behavior are out of scope. If the implementation changes any of those,
that is an undeclared deviation and cannot be GREEN under this brief.

Do not run live Canvas probes and do not use a configured teacher token/course as test
evidence.

## Stop conditions

Stop with RED rather than guessing if:

- A moved phase cannot preserve its existing Canvas call order, digest input, step
  identity, checkpoint timing, exact-ID proof, or failure classification.
- Existing tests reveal that two apparently duplicated helpers have materially
  different semantics; keep them separate rather than normalizing them silently.
- The extraction requires an adapter protocol, registry, route, persistence schema,
  recovery, receipt, autoscore policy, authoring contract, or public API change.
- A leaf module requires importing a facade and creates a cycle.
- A live Canvas call, real course data, credential, student record, or private local
  operation file would be needed to finish.
- An unrelated regression blocks completion.

Return YELLOW rather than guessing if:

- All behavior checks pass but one structural size bound cannot be met without a
  semantic redesign.
- A required verification command is unavailable for an environmental reason.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them
to the senior. Do not leave execution state or test evidence only in chat.

### Execution result

- Traffic light: **GREEN** — implementation, structural bounds, verification, and
  durable closure are complete
- Commit hash: **pre-amend implementation hash `2e69ad5`; final amended hash reported
  at handback**
- Complete committed scope:
  - modified `AGENTS.md` and the Assignment, Quiz, Page, Rubric, and Quick Assignment
    adapter facades;
  - created `adapter_support.py`, `module_placement.py`, `assignment_whole.py`,
    `assignment_tiered.py`, `quiz_steps.py`, `quiz_whole.py`, and
    `quiz_differentiated.py`;
  - created `docs/reference/operation-ledger-module-map.md`;
  - archived this brief and the completed Course Expert retirement brief.
- Focused verification:
  `py -m pytest api/tests/test_operation_ledger.py api/tests/test_operation_routes.py api/tests/test_assignment_operation.py api/tests/test_assignment_tier_operation.py api/tests/test_printable_attach.py api/tests/test_quiz_operation.py api/tests/test_quiz_tier_operation.py api/tests/test_page_operation.py api/tests/test_quick_assignment_operation.py api/tests/test_rubric_operation.py` -> **206 passed, 0 failed**
  `py -m pytest api/tests/test_page_operation.py api/tests/test_quick_assignment_operation.py api/tests/test_rubric_operation.py` -> **62 passed**
- Full verification:
  `py -m pytest api/tests` -> **662 passed, 1 skipped**
  `py tools/size_report.py --root api/operation_ledger/adapters` -> **pass**
  `git diff --check` -> **pass** (LF/CRLF normalization warning for `page.py` only — pre-existing, no diff-check errors)
- Module-placement function sizes:
  `_resolve_or_create_module`: **121 lines**
  `_attach_module_item`: **93 lines**
  `attach_assignment_type_module_item`: **41 lines**
  No function exceeds 180 lines.
- Complete structural result:
  - `assignment.py`: **1446 -> 537 lines**
  - `quiz.py`: **1892 -> 520 lines**
  - full adapters directory: **6757 -> 6388 physical lines** (**-369**)
  - every new module is below 500 lines and every new function is at or below 180
    lines.
- Test patch paths changed: **none**
- Deviations from the brief: **none**. The initial closure metadata described only the
  final module-placement correction; this amended record and commit message account for
  the complete content-adapter decomposition.
- Remaining blocker or decision: **none**
