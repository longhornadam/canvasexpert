# Execution brief: capture the New Quiz grader transport safely

Status: **ready for implementation**

Risk: **high**

Executor: **Luna**

## Outcome

Obtain a de-identified, executable contract for the current first-party New Quiz item-result
grader transport. This is a one-time, user-authorized capability capture against a dummy
course so the later PowerGrader finalization brief can be implemented without inventing a
credential or request shape.

## Locked decisions

- The user explicitly authorized one temporary probe on 2026-07-14 and supplied the dummy
  course and assignment identifiers in chat only. Never copy those identifiers, the Canvas
  base URL, a person, response text, score, tokens, cookies, signed URLs, headers, or raw
  request/response material into this brief, the repository, command output, commit text, or
  handback. Use configured credentials only in memory.
- Validate every launch/read stage before any write. If the first-party launch or a complete
  item-results-plus-fudge payload cannot be derived from observed forms without guessing, do
  not POST; stop RED. Never derive a write from a PAT-only endpoint or an ordinary assignment
  grade write.
- After preflight, one temporary item score/feedback write is permitted. Preserve all other
  item results and the current fudge exactly; issue no automatic retry. Re-fetch the quiz
  session, follow its new authoritative result ID, and verify the change in memory only.
- A verified temporary write remains for the operator to inspect live. Return YELLOW pending
  explicit cleanup direction; do not clear it automatically. An ambiguous outcome is RED,
  with no second write. The later production PowerGrader feature remains out of scope.
- For this capture, a completed Essay response is a supported manual text item even when the
  same result also contains a File Upload item. The probe may change the Essay item only while
  preserving every other item, including the File Upload, exactly. This does not alter the
  locked future product rule that a mixed student finalization routes wholly to SpeedGrader.

## Scope

- Use the existing configured local Canvas session and the operator-provided dummy target to
  observe only the minimum first-party launch, participant/result resolution, read, one
  temporary write, and new-result verification chain.
- Reuse safe parsing ideas in `api/powergrader/new_quiz_fetch.py` only where they match; an
  ephemeral, untracked probe may be used and must be deleted before handback.
- On a verified capture, update `docs/reference/new-quizzes-grading-transport.md` with only
  durable, de-identified field names/stages and add a synthetic de-identified fixture/test
  only if it can validate a narrow parser or contract. Record this execution result here.

## Out of scope

- No PowerGrader UI, session persistence, production write adapter, normal student grading,
  scheduled/bulk writes, cleanup write without a later explicit instruction, or probe source
  or output committed to the repository.

## Reference pattern and routing

- Canonical transport/safety reference: `docs/reference/new-quizzes-grading-transport.md`.
- Read-side launch reference: `api/powergrader/new_quiz_fetch.py::_native_file_transport` and
  `::_resolve_native_candidate`.
- Synthetic New Quiz test patterns: `api/tests/test_powergrader_new_quizzes.py`.
- Read `AGENTS.md` and `TOOLS.md` before broad inspection.

## Implementation requirements

1. Prove the target is a New Quiz and identify one completed dummy Essay response as the
   supported manual text item, without printing identifying or response content. A coexisting
   File Upload item is preserved, not treated as a capture blocker.
2. Record only content-free stage outcomes while resolving the web session, GraphQL preview
   launch, signed grading launch, participant/result credentials, current result, complete item
   collection, and current fudge. Do not expose values in exceptions or logs.
3. Before writing, confirm a complete first-party payload and stable item/result identities.
   Stop RED if any unknown shape would require a guessed operation, credential, or field.
4. Issue at most one permitted temporary write, re-resolve the authoritative result version,
   and verify only boolean/content-free facts. Remove all ephemeral artifacts.
5. If verified, document only the reusable sanitized contract and return YELLOW for operator
   live inspection. If not verified, record RED with whether a write was not issued or its
   outcome is unknown, without disclosure.

## Verification

```powershell
git diff --check
py -m pytest api/tests/test_powergrader_new_quizzes.py
```

Run the live probe only after all no-write stages validate. Do not render a browser route or
start a production grading session for this capture.

## Stop conditions

Stop with RED rather than guessing if:

- Any required launch, participant, result, or item shape is unknown; complete current item
  state/fudge cannot be proven; or a credential would need persistence or disclosure.
- The target is not clearly the user-authorized dummy New Quiz, lacks a safe completed Essay
  response, or a write outcome is ambiguous.
- The capture requires a second write, an automatic rollback, a normal assignment endpoint,
  a public contract expansion, or an unrelated change.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to the
senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **RED**
- Commit hash: `eda6cc3` blocker record; live-preflight update follows in a closure commit
- Files changed: this execution result only
- Verification commands and pass/fail/skip counts: `py -m pytest api/tests/test_powergrader_new_quizzes.py` passed **8** tests; `git diff --check` passed.
- Live probe: content-free assignment preflight confirmed New Quiz; clarified submission/report preflight confirmed one eligible completed Essay response despite a separate File Upload item. No grader launch, credential-resolution, result read, POST, or verification request was issued.
- Deviations from the brief: none.
- Remaining blocker or cleanup decision: although the Essay is eligible, the routed implementation/reference still has no executable web-session/GraphQL submission-preview launch form or complete result/fudge payload contract. The existing code's distinct read-side sessionless/native-file path cannot safely be substituted. A write would require guessing the high-risk credential/result transport. No write was issued, so no cleanup is required.
