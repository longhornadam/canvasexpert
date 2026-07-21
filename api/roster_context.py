"""Pure normalizers for private, course-scoped Roster context.

This module intentionally has no route, configuration, Canvas, or vault imports so
the Web UI and the mirror-only MCP projection share exactly the same validation.
"""

from __future__ import annotations

import math
import re


SEATING_CONTEXT_DEFAULT = {
    "front_row": "none",
    "near_teacher": "none",
    "private_note": "",
    "ai_context_note": "",
}
SEATING_CONTEXT_SUPPORTS = {"none", "preferred", "required"}

SCORE_MATRIX_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")
SCORE_MATRIX_FIELDS = {"columns", "values_by_section"}
SCORE_MATRIX_PATCH_FIELDS = {"columns", "section_id", "values"}

RELATIONSHIP_TYPES = {"keep_apart", "preferred_pair"}
RELATIONSHIP_FIELDS = {"student_a", "student_b", "type", "reason"}


def normalize_seating_context(value: object) -> dict:
    """Return the safe, complete Roster seating-context shape for stored data."""
    context = dict(SEATING_CONTEXT_DEFAULT)
    if not isinstance(value, dict):
        return context
    for key in ("front_row", "near_teacher"):
        if value.get(key) in SEATING_CONTEXT_SUPPORTS:
            context[key] = value[key]
    for key in ("private_note", "ai_context_note"):
        if isinstance(value.get(key), str):
            context[key] = value[key]
    return context


def validate_seating_context(value: object) -> tuple[dict | None, str | None]:
    """Validate one seating-context patch before storage."""
    if not isinstance(value, dict):
        return None, "seating_context must be an object."
    expected = set(SEATING_CONTEXT_DEFAULT)
    supplied = set(value)
    if supplied != expected:
        unknown = sorted(supplied - expected)
        missing = sorted(expected - supplied)
        details = []
        if unknown:
            details.append(f"unknown fields: {unknown}")
        if missing:
            details.append(f"missing fields: {missing}")
        return None, "seating_context must contain exactly the supported fields (" + "; ".join(details) + ")."
    for key in ("front_row", "near_teacher"):
        if value[key] not in SEATING_CONTEXT_SUPPORTS:
            return None, f"seating_context.{key} must be one of {sorted(SEATING_CONTEXT_SUPPORTS)}."
    for key in ("private_note", "ai_context_note"):
        if not isinstance(value[key], str):
            return None, f"seating_context.{key} must be a string."
    context = normalize_seating_context(value)
    return (None if context == SEATING_CONTEXT_DEFAULT else context), None


def _empty_score_matrix() -> dict:
    return {"columns": [], "values_by_section": {}}


def _safe_score_matrix_id(value: object) -> bool:
    return isinstance(value, str) and bool(SCORE_MATRIX_ID_RE.fullmatch(value))


def _finite_score(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validate_score_matrix_columns(columns: object) -> tuple[list[dict] | None, str | None]:
    if not isinstance(columns, list):
        return None, "score-matrix columns must be a list."
    normalized: list[dict] = []
    seen_ids: set[str] = set()
    seen_labels: set[str] = set()
    for index, column in enumerate(columns):
        if not isinstance(column, dict) or set(column) != {"id", "label"}:
            return None, f"score-matrix column {index} must contain exactly id and label."
        column_id = column["id"]
        label = column["label"]
        if not _safe_score_matrix_id(column_id):
            return None, f"score-matrix column {index} has an invalid id."
        if not isinstance(label, str):
            return None, f"score-matrix column {index} label must be a string."
        label = label.strip()
        if not label:
            return None, f"score-matrix column {index} label must not be blank."
        if len(label) > 80:
            return None, f"score-matrix column {index} label must be 80 characters or fewer."
        if column_id in seen_ids:
            return None, f"Duplicate score-matrix column id: {column_id}."
        label_key = label.casefold()
        if label_key in seen_labels:
            return None, f"Duplicate score-matrix column label: {label}."
        seen_ids.add(column_id)
        seen_labels.add(label_key)
        normalized.append({"id": column_id, "label": label})
    return normalized, None


def _normalize_score_matrix(matrix: object) -> dict:
    """Return the complete current-only score-matrix shape for stored local data."""
    if not isinstance(matrix, dict) or set(matrix) - SCORE_MATRIX_FIELDS:
        return _empty_score_matrix()
    columns, error = _validate_score_matrix_columns(matrix.get("columns", []))
    if error:
        return _empty_score_matrix()
    column_ids = {column["id"] for column in columns}
    values_by_section = matrix.get("values_by_section", {})
    if not isinstance(values_by_section, dict):
        return {"columns": columns, "values_by_section": {}}
    normalized_values: dict[str, dict[str, dict[str, int | float]]] = {}
    for section_id, students in values_by_section.items():
        if not _safe_score_matrix_id(section_id) or not isinstance(students, dict):
            continue
        normalized_students: dict[str, dict[str, int | float]] = {}
        for student_id, scores in students.items():
            if not _safe_score_matrix_id(student_id) or not isinstance(scores, dict):
                continue
            normalized_scores = {
                column_id: value for column_id, value in scores.items()
                if column_id in column_ids and _finite_score(value)
            }
            if normalized_scores:
                normalized_students[student_id] = normalized_scores
        if normalized_students:
            normalized_values[section_id] = normalized_students
    return {"columns": columns, "values_by_section": normalized_values}


def _apply_score_matrix_patch(matrix: object, patch: object) -> tuple[dict | None, str | None]:
    """Build one validated local score-matrix update without mutating storage."""
    if not isinstance(patch, dict):
        return None, "score-matrix patch must be an object."
    unknown = set(patch) - SCORE_MATRIX_PATCH_FIELDS
    if unknown:
        return None, f"Unknown score-matrix patch fields: {sorted(unknown)}"
    if "columns" not in patch and "values" not in patch:
        return None, "score-matrix patch needs columns and/or values."
    if "section_id" in patch and "values" not in patch:
        return None, "score-matrix section_id requires values."
    candidate = _normalize_score_matrix(matrix)
    if "columns" in patch:
        columns, error = _validate_score_matrix_columns(patch["columns"])
        if error:
            return None, error
        candidate["columns"] = columns
    valid_column_ids = {column["id"] for column in candidate["columns"]}
    candidate["values_by_section"] = {
        section_id: {
            student_id: {column_id: value for column_id, value in scores.items() if column_id in valid_column_ids}
            for student_id, scores in students.items()
            if any(column_id in valid_column_ids for column_id in scores)
        }
        for section_id, students in candidate["values_by_section"].items()
        if any(any(column_id in valid_column_ids for column_id in scores) for scores in students.values())
    }
    if "values" not in patch:
        return candidate, None
    section_id = patch.get("section_id")
    if not _safe_score_matrix_id(section_id):
        return None, "score-matrix values require a valid section_id."
    values = patch["values"]
    if not isinstance(values, dict):
        return None, "score-matrix values must be an object keyed by student id."
    for student_id, scores in values.items():
        if not _safe_score_matrix_id(student_id):
            return None, "score-matrix values contain an invalid student id."
        if not isinstance(scores, dict):
            return None, f"score-matrix values for student {student_id} must be an object."
        for column_id, value in scores.items():
            if column_id not in valid_column_ids:
                return None, f"Unknown score-matrix column id: {column_id}."
            if value is not None and not _finite_score(value):
                return None, f"score-matrix value for {column_id} must be a finite number or null."
    section_values = {student_id: dict(scores) for student_id, scores in candidate["values_by_section"].get(section_id, {}).items()}
    for student_id, scores in values.items():
        student_values = section_values.get(student_id, {})
        for column_id, value in scores.items():
            if value is None:
                student_values.pop(column_id, None)
            else:
                student_values[column_id] = value
        if student_values:
            section_values[student_id] = student_values
        else:
            section_values.pop(student_id, None)
    if section_values:
        candidate["values_by_section"][section_id] = section_values
    else:
        candidate["values_by_section"].pop(section_id, None)
    return candidate, None


def _empty_relationships() -> dict:
    return {"by_section": {}}


def _normalize_relationship_item(value: object) -> dict | None:
    if not isinstance(value, dict) or set(value) != RELATIONSHIP_FIELDS:
        return None
    student_a = value.get("student_a")
    student_b = value.get("student_b")
    relation_type = value.get("type")
    reason = value.get("reason")
    if not _safe_score_matrix_id(student_a) or not _safe_score_matrix_id(student_b):
        return None
    if student_a == student_b or relation_type not in RELATIONSHIP_TYPES:
        return None
    if not isinstance(reason, str) or len(reason) > 1000:
        return None
    first, second = sorted((student_a, student_b))
    return {"student_a": first, "student_b": second, "type": relation_type, "reason": reason}


def normalize_relationships(value: object) -> dict:
    """Drop malformed relationship records and canonically order the remaining pairs."""
    if not isinstance(value, dict) or set(value) != {"by_section"}:
        return _empty_relationships()
    raw_by_section = value.get("by_section")
    if not isinstance(raw_by_section, dict):
        return _empty_relationships()
    by_section: dict[str, list[dict]] = {}
    for section_id, items in raw_by_section.items():
        if not _safe_score_matrix_id(section_id) or not isinstance(items, list):
            continue
        seen: set[tuple[str, str]] = set()
        normalized: list[dict] = []
        for item in items:
            record = _normalize_relationship_item(item)
            if record is None:
                continue
            pair = (record["student_a"], record["student_b"])
            if pair in seen:
                continue
            seen.add(pair)
            normalized.append(record)
        if normalized:
            by_section[section_id] = sorted(
                normalized,
                key=lambda item: (item["student_a"], item["student_b"], item["type"]),
            )
    return {"by_section": by_section}


def validate_section_relationships(value: object) -> tuple[list[dict] | None, str | None]:
    """Validate a complete replacement list for one section, atomically."""
    if not isinstance(value, list):
        return None, "relationships must be a list."
    normalized: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != RELATIONSHIP_FIELDS:
            return None, f"relationship {index} must contain exactly student_a, student_b, type, and reason."
        student_a = item.get("student_a")
        student_b = item.get("student_b")
        if not _safe_score_matrix_id(student_a) or not _safe_score_matrix_id(student_b):
            return None, f"relationship {index} has an invalid student id."
        if student_a == student_b:
            return None, f"relationship {index} cannot pair a student with themself."
        if item.get("type") not in RELATIONSHIP_TYPES:
            return None, f"relationship {index} has an unsupported type."
        if not isinstance(item.get("reason"), str):
            return None, f"relationship {index} reason must be a string."
        if len(item["reason"]) > 1000:
            return None, f"relationship {index} reason must be 1000 characters or fewer."
        first, second = sorted((student_a, student_b))
        pair = (first, second)
        if pair in seen:
            return None, f"relationship {index} duplicates a pair already in this section."
        seen.add(pair)
        normalized.append({"student_a": first, "student_b": second, "type": item["type"], "reason": item["reason"]})
    return sorted(normalized, key=lambda item: (item["student_a"], item["student_b"], item["type"])), None


def replace_section_relationships(value: object, section_id: object, items: object) -> tuple[dict | None, str | None]:
    """Return a normalized course relationship document with one section replaced."""
    if not _safe_score_matrix_id(section_id):
        return None, "relationships require a valid section_id."
    records, error = validate_section_relationships(items)
    if error:
        return None, error
    candidate = normalize_relationships(value)
    by_section = dict(candidate["by_section"])
    if records:
        by_section[section_id] = records
    else:
        by_section.pop(section_id, None)
    return {"by_section": by_section}, None
