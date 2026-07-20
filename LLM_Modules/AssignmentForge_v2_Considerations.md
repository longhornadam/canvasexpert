# AssignmentForge — v2 Considerations (working notes)

> **Status:** DRAFT. For the next revision of the AssignmentForge contract.
> **Not a contract.** This file does **not** define the JSON envelope — see
> [`AssignmentForge_Base.md`](AssignmentForge_Base.md) (v1.0-json) for that.
> This file captures analysis, candidates, and open questions from the
> 2026-06-11 review against the Canvas LMS Assignments API and the
> follow-up on anonymous grading + LLM-assisted scoring under FERPA.

---

## TL;DR

AssignmentForge v1.0-json covers the highest-value teacher-authored content
(title, description, points, submission type, allowed extensions, external
tool, annotatable file, tiered differentiation). The Canvas Assignment API
exposes roughly thirty additional specifiable fields; v1 leaves most of them
to the Expert tool by design.

v2 should promote a small set of **content decisions** — grading type,
allowed attempts, omit-from-final-grade, peer reviews, true group
assignments, anonymous grading — into the JSON. A separate, larger
opportunity is **LLM-assisted scoring under FERPA**: `anonymous_grading:
true` is *one* of *five* layers needed for a defensible workflow, and the
spec is the right place to declare the others.

---

## 1. Gap analysis: Canvas Assignment fields → spec status

Status legend:

- ✅ **in spec** — the field is in the current v1.0-json JSON
- 🟡 **Expert-only** — the field is wired in the pusher/server but set in the Expert UI, not authored in the JSON
- ❌ **not exposed** — the API supports it; no path from conversation or from the Expert UI
- 🚫 **out of scope** — server-side / Canvas account config, not authored

### 1.1 Identity & content

| Canvas field | JSON path | Status | Notes |
|---|---|---|---|
| `name` | `title` | ✅ | Renamed in spec — fine |
| `description` | `description` | ✅ | HTML string, as required |
| `position` | — | ❌ | Sort order within group; rarely authored; safe to leave Expert-side |
| `assignment_group_id` | — | 🟡 | Server resolves from `assignment_group_name` set in Expert — keep that |
| `integration_id` / `integration_data` | — | 🚫 | SIS vendor plumbing; Expert/IT config |

### 1.2 Points & grading

| Canvas field | JSON path | Status | Notes |
|---|---|---|---|
| `points_possible` | `points` | ✅ | |
| `grading_type` | — | 🟡 | Hard-coded `"points"` in server — should be spec-able |
| `grading_standard_id` | — | 🚫 | Campus-level config; out of scope |
| `omit_from_final_grade` | — | ❌ | Real teacher need ("this is practice, not for the grade") |
| `hide_in_gradebook` | — | ❌ | Useful for surveys/participation assignments |

### 1.3 Submission

| Canvas field | JSON path | Status | Notes |
|---|---|---|---|
| `submission_types` | `submission.types` | ✅ | Full set covered |
| `allowed_extensions` | `submission.allowed_extensions` | ✅ | `"pdf"` and `".pdf"` both accepted — good |
| `external_tool_tag_attributes` (url, new_tab) | `submission.external_tool_url` | ✅ | Pusher hard-codes `new_tab: true` — consider making it spec-able |
| `annotatable_attachment_id` | `submission.annotatable_file` | ✅ | Resolved by name per course — clean |

### 1.4 Dates & visibility

| Canvas field | JSON path | Status | Notes |
|---|---|---|---|
| `due_at` / `unlock_at` / `lock_at` | — | 🟡 | Correctly deferred to Expert — keep as is |
| `only_visible_to_overrides` | — | 🟡 | Server auto-sets for tiered; correct |
| `published` | — | 🟡 | Expert toggle — correct |
| `important_dates` | — | ❌ | Minor; Expert toggle would be enough |

### 1.5 Peer review (a real gap)

| Canvas field | JSON path | Status | Notes |
|---|---|---|---|
| `peer_reviews` | — | ❌ | Real teacher need (writing workshops) |
| `automatic_peer_reviews` | — | ❌ | Implies `peer_reviews: true` |
| `peer_review_count` | — | ❌ | Integer; meaningful with `automatic_peer_reviews` |
| `peer_reviews_assign_at` | — | 🟡 | Expert date picker |
| `intra_group_peer_reviews` | — | ❌ | Boolean; matters only for group assignments |
| `anonymous_peer_reviews` | — | ❌ | Real privacy concern |
| `anonymous_instructor_annotations` | — | ❌ | Boolean |

### 1.6 Group assignment (a real gap)

| Canvas field | JSON path | Status | Notes |
|---|---|---|---|
| `group_category_id` | — | ❌ | The single most important missing field for group projects. Tier mechanism is student-level only; group assignment is a different model |
| `grade_group_students_individually` | — | ❌ | Goes with `group_category_id` |

### 1.7 Attempts & grading workflow

| Canvas field | JSON path | Status | Notes |
|---|---|---|---|
| `allowed_attempts` | — | 🟡 | Hard-coded in QF pusher. Should be spec-able — "students may revise twice" is exactly the kind of thing a teacher would say |
| `anonymous_grading` | — | ❌ | Real classroom need (reduces bias; see §3) |
| `post_manually` | — | 🟡 | New Gradebook feature; Expert toggle is fine |
| `moderated_grading` and friends | — | ❌ | District/IT policy, not conversation content; Expert/IT |

### 1.8 Security / lockdown

| Canvas field | JSON path | Status | Notes |
|---|---|---|---|
| `require_lockdown_browser` | — | ❌ | Campus-administered; Expert toggle is enough |

### 1.9 Out of scope (server-derived / admin-controlled)

`has_overrides`, `all_dates`, `has_submitted_submissions`, `frozen*`,
`needs_grading_count*`, `rubric*`, `score_statistics`, `lock_info`,
`turnitin*`, `vericite_*`, `integration_id`, `can_duplicate`, `original_*`,
`workflow_state` — not authored.

---

## 2. v2 priority additions

### 2.1 Add a `grading` block (high value, low risk)

```json
"grading": {
  "type": "points",                  // "points" | "percent" | "letter_grade" | "gpa_scale" | "pass_fail"
  "anonymous": true,                 // → assignment.anonymous_grading
  "omit_from_final_grade": false,    // → assignment.omit_from_final_grade
  "hide_in_gradebook": false,        // → assignment.hide_in_gradebook
  "allowed_attempts": 1              // → assignment.allowed_attempts (integer; -1 = unlimited)
}
```

### 2.2 Add a `peer_reviews` block (high value for ELA)

```json
"peer_reviews": {
  "required": true,
  "automatic": true,
  "count": 2,
  "anonymous": true,
  "intra_group": false
}
```

### 2.3 Add a true `group` block (NEW capability, not a replacement for tiers)

```json
"group": {
  "category": "<canvas group set name>",   // resolved per course to group_category_id
  "grade_individually": false
}
```

Tiers (current mechanism) handle **differentiation by student** via
per-student overrides — the right tool when "some students get scaffolds,
others get extensions." A `group` block handles **collaborative work**
where one submission represents several students. They solve different
problems and can coexist; v2 should make this distinction explicit so
LLMs don't try to compose them.

### 2.4 Keep the deferral line intact

v1.0-json correctly defers: `due_at`, `unlock_at`, `lock_at`, `published`,
`module_name`, `assignment_group_name`, `grading_standard_id`. v2 should
keep these out of the JSON. They are **delivery** decisions, made per push
in the Expert — not **content** decisions made in the conversation.

---

## 3. LLM-assisted scoring under FERPA

### 3.1 What `anonymous_grading: true` does — and doesn't

When a Canvas assignment has `anonymous_grading: true`, the **grader's
grading screen hides student names and IDs** in the submission list and
submission detail. Canvas keeps the linkage internally so the grade posts
back to the right student.

It does **not**:

- Redact student names from the **submission body** (a student who writes
  "Hi, I'm Jane from 3rd period" identifies themselves in the work)
- Control what the submission body is sent to
- Create any kind of audit trail
- Anonymize anything in third-party systems (Turnitin, an LLM API, etc.)

`anonymous_grading: true` is a grading-UI feature, not a privacy control.

### 3.2 FERPA posture for LLM scoring

FERPA (US) and equivalent student-data-privacy laws (TX-RAMP, UK/EU GDPR
for younger students) regulate **disclosure of PII from education records
to third parties**. Calling an LLM API with a student's name in the prompt
*is* a disclosure to that vendor. The legal posture hinges on:

1. **Is the vendor under contract as a "school official" with a legitimate
   educational interest?** Most majors offer education agreements
   (OpenAI "Data Privacy for Education", Anthropic enterprise terms) that
   route FERPA obligations to the vendor. **Without that contract, it's an
   unauthorized disclosure.**
2. **Is data minimization good?** Full name + full submission + class
   context is more PII than needed. Sending work alone, with a stable
   opaque student ID the LLM never sees, is much safer.
3. **Is there a logging/retention story?** Most consumer LLM APIs log
   prompts and may use them for training. Enterprise/Edu tiers offer
   zero-retention and no-training guarantees. **Consumer tier is a
   non-starter for student work.**

### 3.3 The five layers of a defensible workflow

| # | Layer | Where it lives | What it does | What it doesn't do |
|---|---|---|---|---|
| 1 | Canvas `anonymous_grading: true` | Canvas flag | Hides names from grader UI | Doesn't anonymize submission body; doesn't protect against vendor |
| 2 | Opaque-ID re-routing | Your tool, local | LLM never sees real names/IDs | Doesn't help if you also send the original |
| 3 | Vendor DPA / school-official agreement | Contract | Satisfies FERPA disclosure rules | Doesn't help if you log prompts |
| 4 | Enterprise/Edu tier (zero-retention, no training) | Vendor config | Stops data persisting in vendor logs | Doesn't replace a DPA |
| 5 | Submission-body PII redaction | Your tool, local | Stops students who self-identify in their work | Doesn't help if teacher copy-pastes identifying notes |

**All five are needed.** The spec can authoritatively require #1 and declare
#2; #3 and #4 are teacher/vendor hygiene that the spec can warn about but
not enforce.

### 3.4 Spec additions for LLM scoring

If v2 wants to support LLM-assisted grading as a first-class flow (not a
hidden behavior), the JSON should declare it explicitly:

- A **`rubric` block** — machine-readable criteria with levels and points.
  Required for consistent LLM scoring and reusable for human grading.
- A **`privacy.scoring` field** — `"teacher" | "llm" | "rubric_assisted"`,
  so the pusher can validate, log, and refuse to do it unsafely.
- A **`privacy.redact_pii_in_submissions` field** — best-effort local
  redaction of self-identification in submission text.
- A **Privacy section** in the v2 prose that states the boundary honestly:
  the JSON describes the *assignment*; the teacher is responsible for
  vendor contracts and tier selection.

```json
"rubric": {
  "title": "Argument Essay Rubric",
  "use_for_grading": true,
  "criteria": [
    {
      "name": "Claim",
      "points": 4,
      "levels": [
        { "label": "Strong",   "points": 4, "description": "Clear, specific, defensible claim" },
        { "label": "Adequate", "points": 3, "description": "Claim present but vague or partially defensible" },
        { "label": "Weak",     "points": 1, "description": "Claim unclear or off-task" },
        { "label": "Missing",  "points": 0, "description": "No identifiable claim" }
      ]
    }
  ]
},
"privacy": {
  "scoring": "rubric_assisted",
  "redact_pii_in_submissions": true
}
```

---

## 4. Open questions for the next iteration

1. **Is LLM scoring a v2 feature or a separate spec?** The rubric block and
   privacy.scoring declaration could live in AssignmentForge v2, or in a
   sibling "AssignmentForge-Grade" contract. Argument for a sibling: the
   LLM call needs a configured vendor, which is an **environment**
   decision, not a content decision.
2. **How does the rubric attach?** Canvas API expects a rubric to be
   created and then linked. The pusher resolves `rubric` in the JSON →
   `assignment.use_rubric_for_grading` + an attached rubric object.
3. **Do tiers apply to group assignments?** Tiers assign via student
   overrides; a group assignment has a different visibility model. v2
   should make this composition invalid (or well-defined) rather than
   letting LLM tools combine them implicitly.
4. **External tool `new_tab` — author or default?** Currently hard-coded
   `true`. Trivial to expose as `submission.external_tool_new_tab: false`.
5. **When does the privacy mode get validated?** Should the pusher
   *refuse* to run LLM scoring if `privacy.scoring == "llm"` but the
   configured vendor is consumer-tier? (Yes — but only if v2 defines the
   configuration shape for that.)

---

## 5. Decisions since this review (2026-06-11)

Rubrics were promoted out of §3 and decided ahead of the rest of v2:

- **RubricForge is a fourth contract** — [`RubricForge_Base.md`](RubricForge_Base.md)
  (v1.0-json). One file = one Canvas rubric, dual-register (grader voice +
  student voice), with a self-contained `scoring_guidance` block. Default
  library: `api/rubrics/` (classroom 0–100, STAAR ECR 0–5, STAAR SCR 0–2,
  district ECR 0–10).
- **AF v2 references rubrics by title** (`"rubric": "<title>"`), resolved per
  course like `annotatable_file`; inline rubric authoring in AF is out.
- **Points-match-rubric default:** attaching a rubric for grading sets the
  assignment's `points_possible` to the rubric total; Expert can override to a
  feedback-only association.
- **Student explainer pages:** each rubric defines a simplified student page,
  pushed per course and linked from assignments/quizzes via `{{page:…}}`.
- **No privacy enforcement in tooling** (supersedes §3.3–§3.4 direction):
  `student_name` stays in scoring templates; in-tenant tooling is presumed;
  professional judgment is the teacher's. The product goal is rubrics that
  produce high-quality scoring from humans AND LLMs — not policing.
- Open question 1 is resolved (neither v2 feature nor sibling spec — rubric
  data is RubricForge; no LLM-call machinery in the pusher). Question 2 is
  now RubricForge push behavior. Questions 3–5 remain open.

## 6. References

- [Canvas LMS Assignments API](https://developerdocs.instructure.com/services/canvas/resources/assignments)
- Current spec: [`AssignmentForge_Base.md`](AssignmentForge_Base.md) (v1.0-json)
- Current pusher: [`api/webui/af.py`](../api/webui/af.py), [`api/webui/server.py`](../api/webui/server.py) (`_push_af`)
- FERPA: 34 CFR §99.31(a)(1) — "school official" exception
- Vendor comparisons: OpenAI "Data Privacy for Education", Anthropic
  enterprise terms (as of mid-2026)
