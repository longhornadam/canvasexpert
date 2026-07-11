# Toyota handoff 11c1: RubricForge operation adapter

## Prerequisite and objective

Ferrari has accepted 11c0 (`docs/reference/rubric-live-path.md`). The placeholders below
are filled with authoritative symbols from that discovery.

Migrate the proven parse/validate/prompt path to `content.rubric` — a standalone
rubric push that creates a course-level rubric via Canvas API. Association with a
specific assignment is **not** part of this adapter; it belongs in the
`content.assignment` adapter's rubric step (slice 11c2+).

The adapter parses the canonical contract, validates criteria/ratings/points, confirms
target courses, creates the rubric via Canvas, records returned rubric ID, and migrates
both CourseExpert and standalone Rubric surfaces. Student explainer page creation is
included as an optional step. Association occurs only when explicitly reviewed.

Timeout is `sent_unknown`; same-title matching never proves success. Retry requires
adapter-specific reconciliation. Tests cover cancel, drift, duplicate, ambiguous,
partial, retry, association excluded, redaction, and postcondition.

Stop immediately if evidence contradicts the 11c0 reference doc. One commit; run
operation/route/JS/diff checks and report all IDs.

---

## Authoritative Symbols (from 11c0)

| Placeholder | Value |
|---|---|
| **AUTHORITATIVE_ROUTE** | `POST /api/v1/courses/{course_id}/rubrics` |
| **SERVICE_FUNCTION** | `rf.canvas_rubric_payload(d, course_id)` — builds the Canvas POST body |
| **CANVAS_CREATE_CALL** | `canvas_client._canvas_send("POST", f"/api/v1/courses/{course_id}/rubrics", payload)` → returns `{id, ...}` |
| **ASSOCIATION_POLICY** | Default: course-level bookkeeping (`association_type: "Course"`, `purpose: "bookkeeping"`). Assignment-level association is deferred to the `content.assignment` adapter's rubric step. |
| **EXISTING_TESTS** | `test_rf.py` (4 tests: parse, payload shapes, student page, validation rules). `test_push_service.py::test_rubricforge_content_push_fails_closed_until_wired`. |

---

## Files

- **New** `api/operation_ledger/adapters/rubric.py` — `RubricAdapter` with kind `content.rubric`
- **Modified** `api/operation_ledger/adapters/__init__.py` — register export
- **Modified** `api/operation_ledger/__init__.py` — register + export
- **New** `api/tests/test_rubric_operation.py` — focused adapter/pipeline tests
- **Modified** `api/webui/push_service.py` — replace `_push_rubricforge` blocking body with delegation to the operation-ledger prepare → apply flow
- **Modified** `api/webui/static/push/rubric.js` — send `kind="rf"` → update to `"content.rubric"` or keep routing; coordinate with `api_content_push` dispatch

---

## Adapter Contract

### build_payload
```python
def build_payload(self, prepare_request: dict) -> dict:
    path = prepare_request.get("path")
    # Parse via rf.parse_file(path)
    # Validate version, type, title, criteria, student_page
    # Block tiers (not yet supported)
    # Return {title, criteria, total_points, student_page_title, student_page_body,
    #         publish_explainer, source_path}
```

### source_digest
SHA-256 of `{title, criteria (JSON-sorted), total_points, student_page_title}`.

### verify_targets
Same pattern as `QuickAssignmentAdapter` / `AssignmentAdapter` — validate course_id
against `config.active_courses()`.

### target_key / idempotency_key
```python
target_key = sha256(f"content.rubric|{source_digest}|{course_id}")
idempotency_key = sha256(f"{source_digest}|{course_id}|{normalize_title}")
```

### capture_baseline
`GET /api/v1/courses/{course_id}/rubrics?search_term={title}` → detect existing rubric.

### check_drift
Return `True` if a rubric with the same normalized title already exists.

### freeze_review
Return `{course_name, rubric_title, criteria_count, total_points, student_page_title,
baseline_has_existing, baseline_existing_id}`.

### execute
Two optional steps:
1. **create_rubric** (always): `POST /api/v1/courses/{course_id}/rubrics` with `rf.canvas_rubric_payload(data, course_id)`. Returns rubric ID and association ID.
2. **create_student_page** (if `student_page_title` set): `POST /api/v1/courses/{course_id}/pages` with title + body from `rf.student_page_html(data)`. Follows the same idempotency pattern as PageAdapter's `create_page`.

If no student page title: single step. Module attachment is intentionally excluded (rubrics don't go in modules).

### reconcile
Verify rubric exists by Canvas ID. If student page was created, verify page by slug.

### retry_selector
Standard: unresolved targets (failed, sent_unknown, blocked).

### reversal_descriptor
`{"supported": False, "method": None, "snapshot": None}` — deletion requires Canvas API confirmation before implementation.

---

## Student page handling

The RubricForge contract includes `student_page.title` and `student_page.body`. When
present, the adapter creates a Canvas page with the rendered `rf.student_page_html(data)`.
This is an optional dependent step — if it fails while the rubric succeeded, the
operation status is `partial`.

---

## Assignment-rubric association (NOT in this slice)

Association with a specific assignment uses a different Canvas API shape:
```json
"rubric_association": {
  "association_id": 12345,        // assignment ID
  "association_type": "Assignment",
  "purpose": "grading"
}
```
This will be implemented as a step in the `content.assignment` adapter's execute method
(slice 11c2+), not in this standalone `content.rubric` adapter.

---

## Verification

```powershell
py -m pytest api/tests/test_rubric_operation.py api/tests/test_rf.py api/tests/test_push_service.py api/tests/test_route_contract.py
node --check api/webui/static/push/rubric.js
git diff --check
```

Runtime verification with fakes; live-fire only by explicit authorization.
