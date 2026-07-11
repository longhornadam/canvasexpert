# Rubric Live-Write Path — Discovery Reference

**Author:** Ferrari (11c0 discovery gate)  
**Date:** 2026-07-11  
**Status:** Prepare-only — no live Canvas API write exists

## Executive Summary

The product has **no live Canvas API write path for rubrics**.  Every entry point —
standalone rubric push, assignment push with rubric attachment — is blocked with
"not wired through this push path yet."  The `rf.py` parser contains an **unused**
`canvas_rubric_payload()` that builds the correct payload shape, but it is never
called from any push route.

Claims in `api/README.md` ("Push Rubrics … → live rubrics + student explainer pages")
and `push_rubric.html` ("creates (or reuses) the course rubric and updates the
student explainer page") are **aspirational and false**.

## Call Graph (current)

```
Web UI (Course Expert / standalone Rubric page)
  │
  ├─ POST /api/rf/validate       → rf.parse_file() → rf.summary()     ✅ works
  ├─ GET  /api/rf/scoring-prompt → rf.parse_file() → rf.scoring_prompt() ✅ works
  ├─ POST /api/content/push (kind="rf")
  │    └─ _push_rubricforge()    → rf.parse_file()
  │                               → PushResult(False, "…not wired…")  ❌ blocked
  │
  └─ POST /api/content/push (kind="af", rubric_path set)
       └─ _push_assignmentforge() → PushResult(False, "…not wired…")  ❌ blocked
```

## Modules / Functions

| Module | Function | Role | Has Canvas write? |
|---|---|---|---|
| `api/webui/rf.py` | `parse_file()` | Read + regex envelope + JSON parse + validate | No (pure) |
| `api/webui/rf.py` | `validate()` | 15 validation rules | No (pure) |
| `api/webui/rf.py` | `canvas_rubric_payload(d, course_id)` | Build `POST /rubrics` body (`association_type: "Course"`, `purpose: "bookkeeping"`) | **Never called** |
| `api/webui/rf.py` | `student_page_html(d)` | Render student-facing explainer HTML table | No (pure) |
| `api/webui/rf.py` | `scoring_prompt(d)` | Generate LLM scoring prompt | No (pure) |
| `api/webui/rf.py` | `summary(d)` | Validation summary dict | No (pure) |
| `api/webui/push_service.py` | `_push_rubricforge()` | **Blocks**: not wired | ❌ |
| `api/webui/push_service.py` | `_push_assignmentforge()` | **Blocks** when `rubric_path` set: not wired | ❌ |
| `api/webui/routes/push_validation.py` | `POST /api/rf/validate` | Validate endpoint | No (read-only) |
| `api/webui/routes/push_validation.py` | `GET /api/rf/scoring-prompt` | Prompt generation | No (read-only) |
| `api/webui/routes/push.py` | `POST /api/content/push` | Routes `kind="rf"` → `_push_rubricforge` | ❌ (blocked downstream) |

## Discrepancy Table

| Source | Claim | Reality |
|---|---|---|
| `api/README.md` line 9 | "Push Rubrics (RubricForge JSON → live rubrics + student explainer pages)" | No live push exists |
| `api/README.md` line 40 | "Creates or reuses a course rubric by title, then creates/updates the student explainer page." | No create, no reuse, no page |
| `push_rubric.html` line 22 | "CanvasExpert creates (or reuses) the course rubric and updates the student explainer page." | Both operations blocked |
| `_push_rubricforge()` docstring | (none — returns hardcoded failure) | Refutes all claims above |
| Course Expert rubric tab | Rubric file selector, mode dropdown, explainer checkbox UI | All blocked in backend |
| `rf.canvas_rubric_payload()` docstring | Builds `POST /rubrics` payload | Never called or referenced |

## Capability Verdict

| Capability | Status | Evidence |
|---|---|---|
| Parse & validate RubricForge JSON | ✅ Production | `rf.py` + `test_rf.py` (4 tests) |
| Generate scoring prompt | ✅ Production | `rf.scoring_prompt()` + AI-TA library |
| Render student explainer HTML | ✅ Production | `rf.student_page_html()` (+ teacher CSS in template) |
| Build Canvas REST payload | ✅ Available but unused | `rf.canvas_rubric_payload()` — called only from tests |
| Push rubric to Canvas course | ❌ Not wired | `_push_rubricforge()` always fails |
| Attach rubric to assignment during push | ❌ Not wired | `_push_assignmentforge()` blocks on `rubric_path` |
| Create/update student explainer page | ❌ Not wired | No page creation code in any push path |

## Canvas API Details

### POST /api/v1/courses/{course_id}/rubrics

Creates a rubric at course level.  The response includes both a `rubric` object with
`id` and a `rubric_association` object with `id`.

```json
// Request body shape (from rf.canvas_rubric_payload)
{
  "rubric": {
    "title": "ELA 7 Standard Writing Rubric",
    "free_form_criterion_comments": false,
    "criteria": {
      "0": {
        "description": "Focus & Organization",
        "long_description": "Core question text… consistency thread…",
        "points": 40,
        "criterion_use_range": false,
        "ratings": {
          "0": {"description": "Advanced", "long_description": "…", "points": 40},
          "1": {"description": "Proficient", "long_description": "…", "points": 30},
          ...
        }
      }
    }
  },
  "rubric_association": {
    "association_id": 101,
    "association_type": "Course",
    "purpose": "bookkeeping"
  }
}
```

To create a rubric **and** associate it with a specific **assignment** (not course),
set:
```json
"rubric_association": {
  "association_id": 12345,        // assignment ID
  "association_type": "Assignment",
  "purpose": "grading"            // "grading" not "bookkeeping"
}
```

Canvas does not deduplicate by title — each POST creates a new rubric.  Use
`GET /api/v1/courses/{course_id}/rubrics` with `search_term` for baseline detection.

### Response shape
```json
{
  "id": 789,
  "title": "ELA 7 Standard Writing Rubric",
  "points_possible": 100,
  "reusable": false,
  "public": false,
  "read_only": false,
  "free_form_criterion_comments": false,
  "criteria": [...],
  "rubric_association": {
    "id": 456,
    "association_id": 101,
    "association_type": "Course",
    "purpose": "bookkeeping"
  }
}
```

## Load / Call Order for a Future Adapter

For `content.rubric` (standalone rubric push):

1. Client: `POST /api/content/push` with `kind="rf"`, `{path, published, course_id}`
2. **build_payload**: `rf.parse_file(path)` → validate no tiers, extract `title`, `criteria`, `student_page`
3. **capture_baseline**: `GET /api/v1/courses/{id}/rubrics?search_term={title}` → detect existing
4. **check_drift**: If existing rubric found with same title → block
5. **freeze_review**: Show criteria count, total points, student page config
6. **execute**:
   - Step "create_rubric": `POST /api/v1/courses/{id}/rubrics` with `canvas_rubric_payload()`
   - Step "create_student_page" (if `student_page.title` set): `POST /api/v1/courses/{id}/pages`
7. **reconcile**: Verify rubric exists by ID; verify student page by slug

For **assignment-attached rubric** (via `content.assignment` with `rubric_path`):

The rubric creation and assignment-creation must be in a **single adapter** because
the Canvas API can create both in one call.  The `content.assignment` adapter's
execute would:
1. Build assignment data (as now)
2. If `rubric_path` is set, parse rubric and build combined payload:
   `POST /api/v1/courses/{id}/assignments` with nested rubric data
   — OR —
   `POST /api/v1/courses/{id}/rubrics` with `association_type: "Assignment"` + `association_id: assignment_id`
3. The latter is cleaner: create assignment first, then create rubric with association.

**Recommended architecture**: Two-step:
- Assignment step (existing): creates assignment
- Rubric-attach step (new): creates rubric + associates with assignment in one POST

## Required Tests for 11c1

| Category | Test |
|---|---|
| Positive | Create rubric via Canvas API → returns ID/URL |
| Positive | Create rubric with student page |
| Negative | Unknown rubric file path → ValueError |
| Negative | Canvas error during create → `failed` or `sent_unknown` |
| Negative | Drift: existing rubric with same title → `blocked` |
| Negative | Drift: Canvas error during baseline → `blocked` |
| Retry | Unresolved target → `retry_selector` picks it up |
| Retry | `reconcile` finds rubric by exact ID → `applied` |
| Retry | `reconcile` doesn't find rubric by ID → `sent_unknown` |
| Edge | Empty rubric path in assignment payload → no-op (skip rubric step) |
| Edge | Malformed rubric file → ValueError in `build_payload` |
| Edge | Nested assignment-rubric: assignment succeeds, rubric fails → `partial` |

## 11c1 Insertion Points (authoritative symbols)

Replace these into `docs/handoffs/canvasexpert-redesign-11c1-rubric-operation.md`:

| Placeholder | Value |
|---|---|
| **AUTHORITATIVE_ROUTE** | `POST /api/v1/courses/{course_id}/rubrics` |
| **SERVICE_FUNCTION** | `rf.canvas_rubric_payload(d, course_id)` builds payload; `canvas_client._canvas_send("POST", path, payload)` calls it |
| **CANVAS_CREATE_CALL** | `canvas_client._canvas_send("POST", f"/api/v1/courses/{course_id}/rubrics", payload)` → returns `{id, rubric_association: {id}}` |
| **ASSOCIATION_POLICY** | Default: course-level bookkeeping (`association_type: "Course"`). Assignment-level requires explicit review from the `content.assignment` adapter's rubric step, not from `content.rubric`. |
| **EXISTING_TESTS** | `test_rf.py` (4 tests: parse, payload shapes, student page, validation rules), `test_push_service.py::test_rubricforge_content_push_fails_closed_until_wired` |

## Canonical Doc Corrections Required

Before a live push exists, these documents make false claims:

1. **`api/README.md` lines 9, 40** — Remove or reword rubric push claims to "Prepare-only (scoring prompts, student page preview)"
2. **`api/webui/templates/push_rubric.html` line 22** — Change "creates (or reuses) the course rubric" → "validates and generates a scoring prompt"

These corrections are deferred until 11c1 implementation actually wires the path.