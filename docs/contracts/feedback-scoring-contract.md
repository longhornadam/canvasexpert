# Feedback Scoring Contract - v1

The data contract between **any** scoring LLM and Canvas Expert feedback tools. It is deliberately
LLM-agnostic: OpenRouter, a teacher's own ChatGPT/Claude/MagicSchool session, or a
script can all produce conforming output. Phase C (Push to Canvas) consumes exactly
this output as its input, so this contract is the seam that decouples scoring from
posting. **There is no OpenRouter dependency anywhere in this contract.**

Privacy invariant (non-negotiable): the LLM only ever sees **pseudonyms**. No real
names, Canvas ids, SIS ids, or sections appear in either direction. Re-identification
happens locally via the vault, at push time. See `api/feedback_vault.py`,
`api/feedback_safety.py`, and AGENTS.md guardrail #2 (FERPA).

`contract_version` is `"1.0"`. Bump the major on any breaking change; the validator
(`feedback_pipeline.validate_results`) checks the major version.

## Direction 1 - Bundle (app -> LLM)

What the LLM is asked to score. Produced by `pseudonymize` (New Quizzes CSV) or
`pseudonymize_submissions` (Canvas Assignments API). The LLM receives this plus the
rubric and the scoring instructions (`build_contract_text`).

```json
{
  "contract_version": "1.0",
  "quiz_title": "Essay 1 - Courage",
  "source": "assignment",
  "students": [
    {
      "pseudonym": "S001",
      "responses": [
        {
          "item_id": "4242",
          "prompt": "Write about courage.",
          "response": "Courage is acting despite fear...",
          "possible": 10
        }
      ]
    }
  ]
}
```

- `pseudonym` - opaque, stable per student (vault-assigned). The re-identification key.
- `item_id` - Canvas assignment id (assignments path) or New Quizzes item id. Copied back verbatim.
- `possible` - the item's max points; the LLM scores within `0..possible`.
- Contains **no** identity fields. `feedback_safety.scan_payload` hard-blocks if any leak.

## Direction 2 - Results (LLM -> app)

What the LLM must return. A JSON object is preferred so the version travels with the
data, but a bare array is accepted for backward compatibility:

```json
{
  "contract_version": "1.0",
  "results": [
    {
      "pseudonym": "S001",
      "item_id": "4242",
      "score": 8,
      "feedback": "Glows: clear thesis; strong opening example.\nGrows: tie the second paragraph back to the prompt.\nNext step: add one cited quote as evidence.",
      "disclosure": "Optional persona signoff, if the selected TA persona uses one."
    }
  ]
}
```

Rules enforced by `validate_results`:

| Field | Required | Type | Notes |
|---|---|---|---|
| `pseudonym` | yes | string | Copied verbatim from the bundle. Must exist in the vault. |
| `item_id` | yes | string | Copied verbatim. Must match a `(pseudonym, item_id)` the LLM was given. |
| `score` | yes (key present) | number or null | `null` = comment-only (no grade). Should fall within `0..possible`. |
| `feedback` | yes | non-empty string | Posted as the Canvas submission comment. Follows the selected Feedback Pattern and any selected TA persona signoff policy. |
| `disclosure` | no | string | Optional persona-controlled signoff metadata. Missing is valid when the selected persona has no signoff. |

- **One result per `(pseudonym, item_id)`** in the bundle. Duplicates are an error.
- Out-of-range scores and unscored students are **warnings** (the teacher reviews
  before any push), not hard errors.
- `feedback` is plain text because Canvas comments are plain text. Structure
  (Glows/Grows/Next) lives inside the string, shaped by the chosen Feedback Pattern.
- This contract does **not** require the scorer to identify itself as AI. Any
  student-visible signoff or AI disclosure belongs to the selected TA persona, not
  to this data contract.

### Future (not in v1)

- Per-criterion rubric scoring (`rubric_assessment[criterion_id][points]`) - v1 posts a
  single `score` as `posted_grade`.

## How PowerGrader sessions consume this

The retired FeedbackExpert direct-push routes do not consume this contract. A named
PowerGrader session validates imported results against its SAFE bundle, re-identifies
through the local vault, and uses its frozen review/current-state/idempotency/receipt path
for any Canvas write.

1. Teacher starts a packet-mode PowerGrader session, then pastes or locally selects a
   compatible result JSON file in that session.
2. `validate_results(results, bundle, vault)` must be `ok` (hard errors block; warnings shown).
   A named Copilot batch is validated against that batch's required SAFE bundle. Late
   Copilot batches own their own SAFE-bundle path; an explicitly named path that is missing
   fails closed. Only legacy batches without the field fall back to the session's initial
   top-level bundle.
3. `reidentify(results, vault)` maps `pseudonym` to `canvas_id` / `real_name`.
4. PowerGrader shows local suggestions for teacher edit/approval, freezes the current Canvas
   state before write, and refuses stale or unresolved results.
5. On explicit PowerGrader review confirmation, its guarded submission transport writes:

   ```text
   PUT /api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/{canvas_id}
       submission[posted_grade] = <score>      # omitted when score is null (comment-only)
       comment[text_comment]    = <feedback>   # may include a persona signoff
   ```

   This ordinary Submissions API path works on Assignments today. New Quizzes use a
   separate reviewed item-result adapter: PowerGrader's live-course item-finalization lane
   uses Canvas's first-party, short-lived signed grader transport for teacher-reviewed item
   scores and per-item feedback. It never reuses this assignment-total `PUT`. Active/current
   instructor enrollment is the prerequisite, not PAT-versus-OAuth; concluded, closed,
   past-enrollment, or otherwise restricted courses may return `403`. The lane preserves
   preflight freeze, result-version drift detection, idempotency, post-write verification,
   content-minimized receipts, and fail-closed SpeedGrader fallback; New Quiz scheduled,
   late-catch-up, and interactive automatic posting remain unavailable. See
   `docs/reference/new-quizzes-grading-transport.md`. Late penalties stay in gradebook tools'
   late-sweep, by design.
6. An audit line per push lands in `_audit/` - content-free (counts only), never names/scores.

Ordinarily, the teacher explicitly confirms a PowerGrader push because it changes real grades
and may notify students. Two narrow, default-off exceptions use the same scoring result shape:

- **Scheduled auto-push** is authorized for one scheduled job/assignment.
- **Interactive automatic posting** is authorized only while creating one new assisted or
  packet PowerGrader session. Fast, Classic Quiz, and New Quiz sessions cannot enable it.

Both exceptions are teacher-controlled and must pass fresh Canvas state, assignment policy,
submission identity/drift, idempotency, and writable receipt-directory checks before a grade
and comment PUT. Any missing, changed, excused, already-graded, unsupported, out-of-range, or
otherwise uncertain case remains in the normal review queue. Packet late generation performs
no Canvas write; only a later valid import for that batch can trigger the session-scoped policy.
An automatically posted row is not reopened in Canvas Expert v1; the teacher changes it in
Canvas SpeedGrader.
