# Feedback Scoring Contract — v1

The data contract between **any** scoring LLM and FeedbackExpert. It is deliberately
LLM-agnostic: OpenRouter, a teacher's own ChatGPT/Claude/MagicSchool session, or a
script can all produce conforming output. Phase C (Push to Canvas) consumes exactly
this output as its input — so this contract is the seam that decouples scoring from
posting. **There is no OpenRouter dependency anywhere in this contract.**

Privacy invariant (non-negotiable): the LLM only ever sees **pseudonyms**. No real
names, Canvas ids, SIS ids, or sections appear in either direction. Re-identification
happens locally via the vault, at push time. See `api/feedback_vault.py`,
`api/feedback_safety.py`, and CLAUDE.md guardrail #2 (FERPA).

`contract_version` is `"1.0"`. Bump the major on any breaking change; the validator
(`feedback_pipeline.validate_results`) checks the major version.

---

## Direction 1 — Bundle (app → LLM)

What the LLM is asked to score. Produced by `pseudonymize` (New Quizzes CSV) or
`pseudonymize_submissions` (Canvas Assignments API). The LLM receives this plus the
rubric and the scoring instructions (`build_contract_text`).

```json
{
  "contract_version": "1.0",
  "quiz_title": "Essay 1 — Courage",
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

- `pseudonym` — opaque, stable per student (vault-assigned). The re-identification key.
- `item_id` — Canvas **assignment id** (assignments path) or NQ item id. Copied back verbatim.
- `possible` — the item's max points; the LLM scores within `0..possible`.
- Contains **no** identity fields. `feedback_safety.scan_payload` hard-blocks if any leak.

## Direction 2 — Results (LLM → app)  ⟵ THE OUTPUT CONTRACT

What the LLM must return. A JSON object (a bare array is also accepted for
backward-compat, but the object form is preferred so the version travels with the data):

```json
{
  "contract_version": "1.0",
  "results": [
    {
      "pseudonym": "S001",
      "item_id": "4242",
      "score": 8,
      "feedback": "Glows: clear thesis; strong opening example.\nGrows: tie the second paragraph back to the prompt.\nNext step: add one cited quote as evidence.\n— Sage (AI teaching assistant)",
      "disclosure": "Drafted by Sage (AI), reviewed by your teacher."
    }
  ]
}
```

Rules (enforced by `validate_results`):

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `pseudonym` | yes | string | Copied verbatim from the bundle. Must exist in the vault. |
| `item_id` | yes | string | Copied verbatim. Must match a `(pseudonym, item_id)` the LLM was given. |
| `score` | yes (key present) | number \| null | `null` = comment-only (no grade). Should fall within `0..possible`. |
| `feedback` | yes | non-empty string | Posted **as the Canvas submission comment**. Follows the selected Feedback Pattern and ends with the disclosure. |
| `disclosure` | recommended | string | The honesty line naming the AI-TA. Missing → warning, not error. |

- **One result per `(pseudonym, item_id)`** in the bundle. Duplicates are an error.
- Out-of-range scores and unscored students are **warnings** (the teacher reviews
  before any push), not hard errors.
- `feedback` is plain text — Canvas comments are plain text. Structure (Glows/Grows/
  Next) lives *inside* the string, shaped by the chosen Feedback Pattern.

### Future (not in v1)
- Per-criterion rubric scoring (`rubric_assessment[criterion_id][points]`) — v1 posts a
  single `score` as `posted_grade`.

---

## How Phase C (Push to Canvas) consumes this — BUILT

Implemented in `api/webui/routes/feedback.py` (`/api/feedback/push/preview` + `/push/apply`)
and surfaced as the **Push to Canvas** panel on the Feedback Expert page.

1. Teacher **pastes** the conforming results JSON into the Push panel (no drop folder — the old
   `3_FromLLM` stage was retired with the SAFE/PRIVATE restructure).
2. `validate_results(results, bundle, vault)` → must be `ok` (hard errors block; warnings shown).
   The SAFE bundle is loaded best-effort for coverage/score-range cross-checks.
3. `reidentify(results, vault)` maps `pseudonym → canvas_id / real_name`.
4. In-browser **review preview** (real names, **current Canvas grade**, new score, comment) —
   already-graded rows are unchecked by default (overwrite is opt-in); unresolved pseudonyms
   can't be posted.
5. On explicit count-confirm, push per selected row via `_canvas_send`:
   ```
   PUT /api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/{canvas_id}
       submission[posted_grade] = <score>      # omitted when score is null (comment-only)
       comment[text_comment]    = <feedback>   # includes the AI disclosure
   ```
   Works on **Assignments** today (PAT in active courses). **New Quizzes write-back stays parked**
   (same PAT/403 limit as the report pull). Late penalties are **not** handled here — they stay in
   Gradebook Expert's late-sweep, by design.
6. An audit line per push lands in `_audit/` — **content-free (counts only)**, never names/scores.

Push is **explicitly confirmed** (it changes real grades and notifies students) and
**idempotency-aware** (the preview shows the current grade; graded rows are opt-in to overwrite).
