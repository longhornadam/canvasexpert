# QuizForge operation-ledger design

**Origin:** Historical 11d discovery

**Decision date:** 2026-07-12

**Status:** Implemented architecture reference; the former 11d slices are released.

## Existing live path

Both Quiz UI surfaces currently call GET streaming routes in
`api/webui/routes/push_streaming.py`. Whole-class routes run `qf_pusher.py`; differentiated
routes put browser-supplied manifests (including raw student IDs) into temporary files and
run `push_tiers.py`. `runner.run_streaming` yields human stdout plus a final `[exit N]`.

`qf_pusher.py` currently:

1. parses the QuizForge envelope, merges rationales, inlines stimulus HTML, and transforms
   questions locally;
2. POSTs a New Quiz and retains its returned ID;
3. POSTs each New Quiz item but discards returned item IDs;
4. PUTs the underlying assignment settings;
5. optionally creates/reuses a module and POSTs a module item but discards its ID;
6. prints a URL/success marker and writes only the quiz ID to `.experiment_state.json`.

`push_tiers.py` then creates ad-hoc assignment overrides and visibility patches, storing
raw student IDs in manifests and override IDs in the experiment file. This path cannot
meet write-ahead, exact reconciliation, FERPA minimization, or lost-client guarantees.

## Confirmed Canvas objects

Official Canvas documentation confirms:

- New Quiz create: `POST /api/quiz/v1/courses/{course_id}/quizzes`, returning a NewQuiz.
- New Quiz/item APIs use the assignment-associated quiz ID in the path.
- Item create returns a QuizItem with its exact `id`; exact GET is available at the same
  path plus `/{item_id}`.
- Core assignment overrides accept ad-hoc `student_ids`; exact override GET is available.
- Module items return an exact ID and can be verified by ID/content ID.

Sources:

- <https://developerdocs.instructure.com/services/canvas/resources/new_quizzes>
- <https://developerdocs.instructure.com/services/canvas/resources/new_quiz_items>
- <https://developerdocs.instructure.com/services/canvas/resources/assignments>
- <https://developerdocs.instructure.com/services/canvas/resources/modules>

No separate Stimulus API object is created by the current product: QuizForge stimulus HTML
is intentionally inlined into the attached question payload before item creation.

## Locked decisions

### Planning and subprocess isolation

- Refactor `qf_pusher.py` to expose a pure `build_push_plan(path, settings)` containing
  normalized title, quiz-create payload, ordered item payloads with source item IDs/types,
  assignment settings, and module request.
- Add a CLI JSON-plan mode that performs no Canvas import/call and emits only one JSON
  document. Preparation invokes this mode through a bounded subprocess and validates the
  schema/exit status before persisting the normalized plan.
- The legacy CLI may consume the same pure plan for compatibility, but the Web UI operation
  adapter never invokes the legacy live-write subprocess.

### Targets and differentiated identity

- One operation target remains one selected course.
- Whole mode has one quiz variant. Differentiated mode has ordered variants, each with a
  source file and a **group name**, never browser-supplied student IDs.
- For each course, the server resolves group names within that course's teacher-selected
  Canvas group category using the safe resolver accepted in 11b4. It requires nonempty,
  nonoverlapping groups with exact active-roster coverage and stores only IDs/counts and
  membership digests. Raw student IDs remain transient.
- Existing extra-time configuration is applied in memory to each variant membership,
  producing one or more ad-hoc override buckets. Only bucket counts/digests and date
  effects enter frozen review/baseline; raw IDs never persist.

### Ordered mutation steps

For each course/variant in source order:

1. `create_quiz:{variant}` — POST New Quiz; checkpoint quiz/assignment ID and URL.
2. For differentiated variants, `restrict_assignment:{variant}` — PUT the underlying
   assignment with `only_visible_to_overrides=true` before any possible publish.
3. `create_override:{variant}:{bucket}` — POST each transient ad-hoc student override and
   checkpoint its exact ID.
4. `create_item:{variant}:{item}` — POST each ordered item and checkpoint exact item ID.
5. `patch_assignment:{variant}` — apply requested dates/category/SIS/publish settings and
   verify the exact assignment. A rejected requested effect is partial, never a warning
   reported as success.
6. `create_module` once per course if needed, then `attach_module:{variant}` for each quiz
   assignment with exact module-item ID verification.

Same-title matching never proves success. Before first write, unknown same-title New Quiz
assignments block. After partial execution, only exact IDs in durable steps are excluded
from drift. Missing returned IDs or uncertain transport are `sent_unknown`; definitive
failure after a prior successful step is `partial`; retry verifies exact completed IDs and
resumes the first unfinished step.

### Durable progress and lost clients

- Operation records gain a bounded safe event list with monotonic sequence, timestamp,
  hashed target key, step key, state, and a fixed message code. No payload, title, path,
  course/student ID, diagnostic, or free text is allowed.
- `ExecutionContext.before_send` and `checkpoint_step` append events atomically with the
  step mutation. Operation terminal status appends a final event.
- A PII-minimized SSE endpoint streams stored events by operation ID and sequence, supports
  reconnect, and closes only when the operation is terminal.
- Long apply runs via `asyncio.to_thread` (or equivalent existing threadpool mechanism) so
  the event loop can serve SSE and cancelling the browser request cannot kill the worker
  thread. Duplicate apply remains fenced by operation status/claims.
- Startup calls ledger recovery. Recovery reconciles claimed/sent-unknown quiz steps by
  exact IDs and finalizes operation status/receipt when all targets become terminal.

### Browser and compatibility

- `quiz.js` prepares `content.quiz` through the shared selected-target envelope. Whole
  mode sends one path/settings; differentiated mode sends ordered `{path, group_name}`
  variants. It sends no course manifest, Canvas URL, group ID, or student ID.
- Shared review displays server-frozen quiz/item counts, settings, group/count rows, and
  extra-time bucket counts. Apply opens the operation SSE and renders durable step progress.
- Both Course Expert and standalone Quiz use the same path. Existing live streaming routes
  become fail-closed compatibility responses (HTTP 410/no write) after migration. Preview
  remains a no-network planner operation.
- `qf_pusher.py` and `push_tiers.py` remain explicit manual CLI tools; they are not reachable
  from a migrated browser live-write control.

## Slice order

1. **11d1 — plan and whole-class adapter:** pure subprocess plan, direct checkpointed
   quiz/item/settings/module writes, exact reconciliation, registered kind, fake tests.
   Browser remains on the legacy path until acceptance.
2. **11d2 — differentiation:** safe group/extra-time resolution and checkpointed override
   steps. Implemented — two or more ordered variants with group-restricted overrides.
   Browser still remains legacy.
3. **11d3 — progress polling endpoint:** `GET /api/operations/{id}/status` returning
   PII-minimized target/step states. No SSE, no event log, no asyncio threading.
   Browser polling loop can be wired post-release.

All three slices are released. Browser migration from legacy streaming to the polling
endpoint is deferred to post-release.
