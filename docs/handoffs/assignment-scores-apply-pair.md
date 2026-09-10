# Brief: post assignment scores and feedback from chat

**Status:** current
**Risk:** High (writes real grades and student-visible comments)
**Senior decision date:** 2026-09-10

## Objective

An agent that has scored a PowerGrader session can land those scores and comments in
Canvas from the conversation, through a frozen review the teacher reads and answers.

Today it dead-ends. `stage_scores` says so outright — *"Does NOT post to Canvas, even if
auto_post is enabled (teacher pushes manually via the queue)."* New Quizzes got a write
lane (`preview_new_quiz_scores` / `apply_new_quiz_scores`); ordinary assignments never
did. That asymmetry is an accident of build order, not a considered rule.

Review is not being removed. It moves into the conversation, where the teacher already
is, instead of parking work in a queue they have to go visit. This matches the principle
the MCP server already states for the New Quiz lane: *"Asking for the write is the
authorization, so run it and report what landed rather than asking again."*

## Locked decisions

### 1. Preview performs the local approval. Apply performs the Canvas write.

This is forced by the existing seams, and it is the one surprising part of the design.

`review_push` freezes `payload_digests` from `_payload(student)`, which reads
`teacher_score` / `teacher_feedback` — not `ai_score` / `ai_feedback`. And
`_eligible_students` requires `status == "approved"`. So a review cannot be frozen over
rows that have not been approved yet: it would freeze empty payloads.

Therefore `preview_assignment_scores`, inside the session lock:

1. copies `ai_score` → `teacher_score` and `ai_feedback` → `teacher_feedback` for the
   rows in scope, setting `status = "approved"`;
2. freezes the review via `review_push`.

Nothing reaches Canvas. A preview the teacher never applies leaves those rows approved in
the PowerGrader queue — the same end state as approving them in the UI and not pushing.
Say this plainly in the tool docstring; a teacher must not discover it.

`_eligible_students` gains an explicit `statuses` parameter (default `("approved",)`) so
the chat path can select `pending` rows without changing the web UI path.

### 2. Ambiguity is raised as a question that blocks apply.

The preview returns `questions`. `apply_assignment_scores` refuses with
`unanswered_questions` unless every blocking question has an answer, and the answer
changes what lands. A question the agent can ignore is not a question.

| `kind` | Raised when | `options` |
|---|---|---|
| `score_above_possible` | staged score exceeds the item's `possible` | `post_anyway` \| `skip_those` |
| `overwrites_existing_score` | the frozen baseline already carries a score | `overwrite` \| `skip_those` |
| `missing_score` | a row has feedback but no score | `comment_only` \| `skip_those` |
| `pseudonym_in_feedback` | outgoing feedback contains a vault pseudonym | `skip_those` \| `post_anyway` |
| `held_not_scored` | students whose only responses were held, so they receive nothing | `proceed` \| `stop` |

Informational facts that do not change what lands (counts, totals) go in `notes`, not
`questions`. Do not inflate the question list; a teacher who is asked five things every
time will stop reading them.

`pseudonym_in_feedback` is the enforcement half of the scoring rule added in `90352da`.
Scrubbing is whole-word and over-corrects, so an AI that quotes a response can quote a
substituted token straight back at the student. The contract now tells it not to; this
catches it at the write boundary, where it is checkable.

### 3. Pseudonyms at the boundary. Always.

`review_push` and `push_grades` are `user_id`-native. Resolution happens inside the tool
layer against the local vault. No `user_id` appears in a parameter, a return value, a
question, a note, or an error. This is the highest-risk seam in the slice.

### 4. Reuse the existing transport whole.

`review_push` for the freeze, `push_grades` for the write. They already carry the review
token, TTL, drift check against a fresh Canvas snapshot, per-target digests, and the
`_review_error` vocabulary (`review_expired`, `payload_changed`, `drift_detected`, …).
Do not add an operation-ledger kind, and do not write a second push path.

### 5. New Quiz sessions are refused, not handled.

`_writeback_mode` returns `comments_only` for them, and they have their own
item-finalization lane. Refuse with a message naming `preview_new_quiz_scores`.

### 6. Approving from chat is not a blind-first datapoint.

`save_student` records `blind_first.record_implicit_blind` because a teacher who scores
without revealing the AI suggestion is the cleanest blind datapoint there is. Copying an
AI score into `teacher_score` is the opposite. Do not record it as blind; preserve the
provenance honestly.

Attribution needs no work: `_payload` already routes assistant-authored feedback through
`attribution.attribute`, so AI-drafted words do not reach a student under the teacher's
name.

## Scope

| File | Change |
|---|---|
| `api/powergrader/session_actions.py` | `_eligible_students` gains `statuses`; `review_push` passes it through. No behavior change at the default. |
| `api/powergrader/scoring_apply.py` | New. Question computation, the approval copy, and the two entry points the MCP layer calls. |
| `api/mcp_server/tools.py` | `preview_assignment_scores(scoring_session_id, pseudonyms=None)`, `apply_assignment_scores(scoring_session_id, review_digest, answers)`. Pseudonym resolution and the safety gate live here. |
| `api/mcp_server/server.py` | Both wrappers. |
| `api/mcp_server/contract.py` + `tool_schema_v43.json` | 42 → 43; 46 → 48 tools. |
| `docs/mcp-server.md` | Two rows; the "six tools reach Canvas" count moves to eight. |
| `docs/contracts/canvas-transport-owners.json` | The write already has an owner via `push_grades`; confirm it still matches and add one only if a new call site appears. |

## Acceptance criteria

1. Preview over a session with staged scores returns aggregate counts, `questions`, and a
   `review_digest`, and makes no Canvas write.
2. Apply lands exactly the frozen review through `push_grades`, and the pushed rows are
   marked `posted`.
3. Apply refuses with `unanswered_questions` when any blocking question lacks an answer,
   and makes no Canvas call.
4. Each question's answer demonstrably changes what lands — `skip_those` omits those rows
   from the write.
5. Canvas changing between preview and apply yields `drift_detected` from the existing
   check, with no partial write.
6. Re-applying the same `review_digest` is a no-op with a clear status, not a second push.
7. No `user_id` appears anywhere in either tool's output, including error and question
   text. Asserted directly.
8. A New Quiz session is refused with a message naming the New Quiz lane.
9. The web UI queue path is unchanged: existing `review_push` / `push_grades` tests pass
   untouched.

## Non-goals

- Attachment/media text extraction. `held` rows stay held; this slice only *surfaces*
  them as a question. That is its own slice.
- Any change to auto-post policy, the scheduled job, or the interactive opt-in.
- Web UI changes. The queue keeps working exactly as it does.
- An operation-ledger kind for this write.

## Verification gate

```powershell
py -m pytest api/tests/powergrader/ api/tests/mcp_server/ api/tests/test_powergrader_manual_push.py -p no:randomly
```

- **Law:** no `user_id` in any preview/apply output, over a session whose vault has known ids.
- **Law:** apply refuses while a blocking question is unanswered, and issues no Canvas call.
- **Contract:** every question `kind` the preview can emit is answerable, and each option
  is honored by apply — parametrized over the kind list, so a new kind is covered.
- **Example:** one happy path — preview, answer, apply, assert one push and `posted` set.

Canvas is faked at the `canvas_send` / `canvas_get` injection points these functions
already take. **No live scoring run against real student data.**

## Stop conditions

- Stop if the approval-in-preview ordering (locked decision 1) turns out to be avoidable
  — if payloads can be frozen without mutating session state, that is the better design
  and a senior decision.
- Stop if `push_grades` cannot be driven with a frozen review produced outside the HTTP
  route layer.
- Stop if any question kind cannot be computed without reading a real name.

## Execution result

_(executor fills in: traffic light, changed files, commands and counts, deviations,
unresolved decisions)_
