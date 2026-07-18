# Course Catalog v1 contract

Course Catalog is Canvas Expert's durable, student-data-free projection of assignment and
module metadata for one configured **Current** course. Its first consumer is the PowerGrader
setup picker. It is a local navigation/search authority only: Canvas remains authoritative
for focused assignment state, submissions, evidence, grades, comments, and every write.

## Location and identity

Each course owns two files below the configured synced workspace:

```text
_System/Canvas Catalog/<canvas-course-id>/catalog.v1.json
_System/Canvas Catalog/<canvas-course-id>/catalog.v1.previous.json
```

The Canvas course ID, not a display name, is directory identity. Previous-course catalogs
remain on disk, but the HTTP routes may read or refresh only courses returned by
`config.active_courses()`.

## Root and scope schema

Every persisted document has exactly these root keys:

```json
{
  "version": 1,
  "course_id": "course-id",
  "course_name": "Teacher-facing course label",
  "updated_at": "ISO-8601 timestamp",
  "assignments": {
    "state": "current",
    "last_success_at": "ISO-8601 timestamp or empty",
    "last_attempt_at": "ISO-8601 timestamp or empty",
    "error_code": "sanitized stable code or empty",
    "records": {}
  },
  "modules": {
    "state": "current",
    "last_success_at": "ISO-8601 timestamp or empty",
    "last_attempt_at": "ISO-8601 timestamp or empty",
    "error_code": "sanitized stable code or empty",
    "records": []
  }
}
```

Allowed scope states are `current`, `stale`, `incomplete`, and `unavailable`:

- `current`: the latest requested scope acquisition completed. A fully successful, fully
  paginated empty top-level assignment or module collection is current and authoritative.
- `stale`: last-good records remain usable after a scope acquisition failed or returned an
  unproven collection result.
- `incomplete`: acquisition produced useful records but rejected an invalid record or could
  not acquire every omitted module-item list.
- `unavailable`: no last-good records exist for the failed scope.

The two scopes merge independently. Failed or incomplete top-level collection reads retain
last-good records; a proven-complete empty collection replaces them. A complete collection
with a missing/invalid top-level record or duplicate normalized ID is `incomplete` and also
retains last-good membership. Before any successful scope exists, its valid unique subset may
be stored as `incomplete`; a collection with no valid records remains `unavailable`. A
successful module-list acquisition may retain previous items for an individual module whose
fallback item request fails; the module scope is then `incomplete`.

## Assignment allowlist

`assignments.records` is keyed by stable Canvas assignment ID. The key must equal the
record's `id`. Each record has exactly:

- `id`, `name`, and normalized `description_text`;
- `points_possible`;
- `due_at`, `unlock_at`, `lock_at`, `created_at`, and `updated_at`;
- `published`, `submission_types`, and `assignment_group_id`;
- `quiz_id`, `is_quiz`, `quiz_kind`, and `is_quiz_lti_assignment`;
- `rubric`, containing allowlisted criteria and ratings only;
- `rubric_settings`, containing only ID, title, points, free-form-comment, score-total,
  points, and outcome-display settings.

Rubric criteria retain only `id`, normalized `description`/`long_description`, `points`, and
ratings. Ratings retain only `id`, normalized descriptions, and `points`. Raw assignment
HTML is converted to plain searchable text and is not persisted.

## Module allowlist

`modules.records` is an ordered list in Canvas course position. Each module has exactly
`id`, `name`, `position`, and ordered `items`. Each item has exactly `id`, `type`, `title`,
`position`, and `content_id`. Inline `items: []` is a known empty module. A missing `items`
field triggers the bounded module-items fallback.

Derived `assignment_ids` and `quiz_ids` may appear in an HTTP projection for PowerGrader;
they are not persisted fields.

## Forbidden material

The catalog must never contain raw Canvas responses, raw HTML, users, enrollments,
submissions, attempts, grades, comments, attachments, student identifiers, authorization
material, signed URLs, Canvas transport URLs, private local paths, or arbitrary unapproved
Canvas fields. Validation rejects unknown root, scope, assignment, rubric, module, and
module-item keys before storage.

## Acquisition and writes

A refresh concurrently requests the complete assignment collection and the complete module
collection. Only a successful, complete list receipt may replace top-level membership; a
transport failure, incomplete pagination, or invalid collection root leaves last-good records
in place. Modules request `include[]=items`; modules that omit the field use a fixed,
small-concurrency module-items fallback. Refresh never performs assignment-detail N+1
requests and never performs a Canvas mutation.

`GET /api/course-catalog?course_id=...` is disk-only. `POST
/api/course-catalog/refresh` performs the read-only acquisition. Both routes enforce the
Current-course boundary and return sanitized state/warnings without filesystem paths or raw
Canvas errors.

## Durability and OneDrive behavior

The complete document is validated before every write. Writes use a same-directory
temporary file, flush, `fsync`, and `os.replace`. Before replacement, a validated canonical
snapshot becomes `catalog.v1.previous.json`. A corrupt canonical file is quarantined and a
validated previous snapshot is used when available; a corrupt previous snapshot is also
quarantined and is not treated as usable state.

OneDrive-style competing catalog files are never merged, selected, renamed, or deleted.
Canvas Expert continues from the validated canonical/previous file, returns the stable
`competing_catalog_files` warning, and may rebuild the canonical snapshot on a later
successful refresh. Per-course refresh locks are process-local only; the catalog does not
claim distributed or transactionally consistent Canvas state.
