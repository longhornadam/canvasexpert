"""Durable, student-data-free Canvas course metadata projection.

The catalog is a local read model for navigation and search. Canvas remains the
authority for focused reads and every write. Only the explicit v1 allowlists in
this module may enter the configured synced workspace.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

from api.assignment_collection import (
    ASSIGNMENTS_PATH,
    AssignmentCollectionReceipt,
    acquire_assignment_collection,
)
from api.webui import workspace


CATALOG_VERSION = 2
CATALOG_V1_VERSION = 1
CATALOG_STATES = {"current", "stale", "incomplete", "unavailable"}
ROOT_KEYS = {"version", "course_id", "course_name", "updated_at", "assignments", "modules", "assignment_groups"}
V1_ROOT_KEYS = ROOT_KEYS - {"assignment_groups"}
SCOPE_KEYS = {"state", "last_success_at", "last_attempt_at", "error_code", "records"}
ASSIGNMENT_KEYS = {
    "id", "name", "description_text", "points_possible", "due_at", "unlock_at", "lock_at",
    "created_at", "updated_at", "published", "submission_types", "assignment_group_id",
    "quiz_id", "is_quiz", "quiz_kind", "is_quiz_lti_assignment", "rubric", "rubric_settings",
}
RUBRIC_CRITERION_KEYS = {"id", "description", "long_description", "points", "ratings"}
RUBRIC_RATING_KEYS = {"id", "description", "long_description", "points"}
RUBRIC_SETTINGS_KEYS = {
    "id", "title", "points_possible", "free_form_criterion_comments",
    "hide_score_total_for_assessment", "hide_points", "hide_outcome_results",
}
MODULE_KEYS = {"id", "name", "position", "items"}
MODULE_ITEM_KEYS = {"id", "type", "title", "position", "content_id"}
ASSIGNMENT_GROUP_KEYS = {"id", "name", "position", "group_weight"}

MODULES_PATH = "/api/v1/courses/{course_id}/modules"
MODULE_ITEMS_PATH = "/api/v1/courses/{course_id}/modules/{module_id}/items"
ASSIGNMENT_GROUPS_PATH = "/api/v1/courses/{course_id}/assignment_groups"
MODULE_ITEM_CONCURRENCY = 3

CanvasGetAll = Callable[[str, dict], tuple[list | None, str | None]]
CanvasGetAllComplete = Callable[[str, dict], tuple[object, str | None, bool]]

_LOCKS_GUARD = threading.Lock()
_COURSE_LOCKS: dict[str, threading.RLock] = {}


class _DescriptionText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style"}:
            self.ignored_depth += 1
        elif tag.lower() in {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style"} and self.ignored_depth:
            self.ignored_depth -= 1
        elif tag.lower() in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.ignored_depth:
            self.parts.append(data)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_text(value) -> str:
    return " ".join(str(value or "").split())


def _description_text(value) -> str:
    parser = _DescriptionText()
    try:
        parser.feed(str(value or ""))
        parser.close()
    except (TypeError, ValueError):
        text = _normalize_text(value)
    else:
        text = _normalize_text(" ".join(parser.parts))
    return re.sub(r"\b(?:https?://|www\.)\S+", "[link]", text, flags=re.IGNORECASE)


def _id(value) -> str:
    return str(value).strip() if value is not None else ""


def _position(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    return value if isinstance(value, (int, float)) else None


def _timestamp(value) -> str:
    return str(value or "").strip()


def _valid_iso(value: str, *, allow_empty: bool = False) -> bool:
    if value == "" and allow_empty:
        return True
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return True


def _require_exact_keys(value, keys: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} schema is invalid")


def _validate_rubric(rubric) -> None:
    if not isinstance(rubric, list):
        raise ValueError("assignment rubric must be a list")
    for criterion in rubric:
        _require_exact_keys(criterion, RUBRIC_CRITERION_KEYS, "rubric criterion")
        if not criterion["id"] or not isinstance(criterion["id"], str):
            raise ValueError("rubric criterion id is invalid")
        if not all(isinstance(criterion[key], str) for key in ("description", "long_description")):
            raise ValueError("rubric criterion text is invalid")
        if criterion["points"] is not None and not isinstance(criterion["points"], (int, float)):
            raise ValueError("rubric criterion points are invalid")
        if not isinstance(criterion["ratings"], list):
            raise ValueError("rubric ratings are invalid")
        for rating in criterion["ratings"]:
            _require_exact_keys(rating, RUBRIC_RATING_KEYS, "rubric rating")
            if not rating["id"] or not isinstance(rating["id"], str):
                raise ValueError("rubric rating id is invalid")
            if not all(isinstance(rating[key], str) for key in ("description", "long_description")):
                raise ValueError("rubric rating text is invalid")
            if rating["points"] is not None and not isinstance(rating["points"], (int, float)):
                raise ValueError("rubric rating points are invalid")


def _validate_assignment(record: dict, expected_id: str) -> None:
    _require_exact_keys(record, ASSIGNMENT_KEYS, "assignment")
    if record["id"] != expected_id or not expected_id:
        raise ValueError("assignment stable id is invalid")
    for key in (
        "id", "name", "description_text", "due_at", "unlock_at", "lock_at", "created_at",
        "updated_at", "assignment_group_id", "quiz_id", "quiz_kind",
    ):
        if not isinstance(record[key], str):
            raise ValueError(f"assignment {key} is invalid")
    if record["points_possible"] is not None and not isinstance(record["points_possible"], (int, float)):
        raise ValueError("assignment points are invalid")
    if not all(isinstance(record[key], bool) for key in ("published", "is_quiz", "is_quiz_lti_assignment")):
        raise ValueError("assignment flags are invalid")
    if not isinstance(record["submission_types"], list) or not all(isinstance(v, str) for v in record["submission_types"]):
        raise ValueError("assignment submission types are invalid")
    _validate_rubric(record["rubric"])
    _require_exact_keys(record["rubric_settings"], RUBRIC_SETTINGS_KEYS, "rubric settings")
    for key, value in record["rubric_settings"].items():
        if key in {"points_possible"}:
            if value is not None and not isinstance(value, (int, float)):
                raise ValueError("rubric settings points are invalid")
        elif key in {"free_form_criterion_comments", "hide_score_total_for_assessment", "hide_points", "hide_outcome_results"}:
            if not isinstance(value, bool):
                raise ValueError("rubric settings flags are invalid")
        elif not isinstance(value, str):
            raise ValueError("rubric settings text is invalid")


def _validate_modules(records) -> None:
    if not isinstance(records, list):
        raise ValueError("module records must be a list")
    seen_modules: set[str] = set()
    for module in records:
        _require_exact_keys(module, MODULE_KEYS, "module")
        module_id = module["id"]
        if not isinstance(module_id, str) or not module_id or module_id in seen_modules:
            raise ValueError("module stable id is invalid")
        seen_modules.add(module_id)
        if not isinstance(module["name"], str) or not isinstance(module["position"], int):
            raise ValueError("module fields are invalid")
        if not isinstance(module["items"], list):
            raise ValueError("module items must be a list")
        seen_items: set[str] = set()
        for item in module["items"]:
            _require_exact_keys(item, MODULE_ITEM_KEYS, "module item")
            item_id = item["id"]
            if not isinstance(item_id, str) or not item_id or item_id in seen_items:
                raise ValueError("module item stable id is invalid")
            seen_items.add(item_id)
            if not all(isinstance(item[key], str) for key in ("type", "title", "content_id")):
                raise ValueError("module item text is invalid")
            if not isinstance(item["position"], int):
                raise ValueError("module item position is invalid")


def _validate_assignment_groups(records) -> None:
    if not isinstance(records, list):
        raise ValueError("assignment group records must be a list")
    seen_ids: set[str] = set()
    for group in records:
        _require_exact_keys(group, ASSIGNMENT_GROUP_KEYS, "assignment group")
        group_id = group["id"]
        if not isinstance(group_id, str) or not group_id or group_id in seen_ids:
            raise ValueError("assignment group stable id is invalid")
        seen_ids.add(group_id)
        if not isinstance(group["name"], str) or not isinstance(group["position"], int):
            raise ValueError("assignment group fields are invalid")
        if isinstance(group["group_weight"], bool) or not isinstance(group["group_weight"], (int, float)):
            raise ValueError("assignment group weight is invalid")


def validate_catalog(document: dict) -> dict:
    """Validate a strict v1 compatibility or canonical v2 document."""
    if not isinstance(document, dict) or document.get("version") not in {CATALOG_V1_VERSION, CATALOG_VERSION}:
        raise ValueError("catalog version is invalid")
    version = document["version"]
    _require_exact_keys(document, ROOT_KEYS if version == CATALOG_VERSION else V1_ROOT_KEYS, "catalog")
    if not isinstance(document["course_id"], str) or not document["course_id"]:
        raise ValueError("catalog course id is invalid")
    if not isinstance(document["course_name"], str) or not _valid_iso(document["updated_at"]):
        raise ValueError("catalog identity or timestamp is invalid")
    for scope_name in ("assignments", "modules"):
        scope = document[scope_name]
        _require_exact_keys(scope, SCOPE_KEYS, f"{scope_name} scope")
        if scope["state"] not in CATALOG_STATES:
            raise ValueError(f"{scope_name} state is invalid")
        if not _valid_iso(scope["last_success_at"], allow_empty=True) or not _valid_iso(scope["last_attempt_at"], allow_empty=True):
            raise ValueError(f"{scope_name} timestamps are invalid")
        if not isinstance(scope["error_code"], str):
            raise ValueError(f"{scope_name} error code is invalid")
        if scope_name == "assignments":
            if not isinstance(scope["records"], dict):
                raise ValueError("assignment records must be an object")
            for assignment_id, record in scope["records"].items():
                if not isinstance(assignment_id, str):
                    raise ValueError("assignment key is invalid")
                _validate_assignment(record, assignment_id)
        else:
            _validate_modules(scope["records"])
    if version == CATALOG_VERSION:
        scope = document["assignment_groups"]
        _require_exact_keys(scope, SCOPE_KEYS, "assignment groups scope")
        if scope["state"] not in CATALOG_STATES:
            raise ValueError("assignment groups state is invalid")
        if not _valid_iso(scope["last_success_at"], allow_empty=True) or not _valid_iso(scope["last_attempt_at"], allow_empty=True):
            raise ValueError("assignment groups timestamps are invalid")
        if not isinstance(scope["error_code"], str):
            raise ValueError("assignment groups error code is invalid")
        _validate_assignment_groups(scope["records"])
    return document


def _normalize_rubric(value) -> list[dict]:
    out = []
    for criterion in value if isinstance(value, list) else []:
        if not isinstance(criterion, dict) or not _id(criterion.get("id")):
            continue
        ratings = []
        for rating in criterion.get("ratings") if isinstance(criterion.get("ratings"), list) else []:
            if not isinstance(rating, dict) or not _id(rating.get("id")):
                continue
            ratings.append({
                "id": _id(rating.get("id")),
                "description": _description_text(rating.get("description")),
                "long_description": _description_text(rating.get("long_description")),
                "points": _number(rating.get("points")),
            })
        out.append({
            "id": _id(criterion.get("id")),
            "description": _description_text(criterion.get("description")),
            "long_description": _description_text(criterion.get("long_description")),
            "points": _number(criterion.get("points")),
            "ratings": ratings,
        })
    return out


def _normalize_rubric_settings(value) -> dict:
    source = value if isinstance(value, dict) else {}
    return {
        "id": _id(source.get("id")),
        "title": _normalize_text(source.get("title")),
        "points_possible": _number(source.get("points_possible")),
        "free_form_criterion_comments": source.get("free_form_criterion_comments") is True,
        "hide_score_total_for_assessment": source.get("hide_score_total_for_assessment") is True,
        "hide_points": source.get("hide_points") is True,
        "hide_outcome_results": source.get("hide_outcome_results") is True,
    }


def _quiz_classification(row: dict) -> tuple[bool, str]:
    submission_types = row.get("submission_types") if isinstance(row.get("submission_types"), list) else []
    quiz_type = str(row.get("quiz_type") or "").lower()
    is_lti = row.get("is_quiz_lti_assignment") is True
    is_quiz = bool("online_quiz" in submission_types or row.get("quiz_id") is not None or row.get("quiz_type") is not None or is_lti)
    if is_lti:
        return is_quiz, "new_quiz"
    if "online_quiz" in submission_types:
        if "new_quiz" in quiz_type or quiz_type == "quizzes.next":
            return is_quiz, "new_quiz"
        external = row.get("external_tool_tag_attributes")
        if isinstance(external, dict):
            hint = f"{external.get('url') or ''} {external.get('content_type') or ''}".lower()
            if "quiz" in hint or "new_quiz" in hint:
                return is_quiz, "new_quiz"
        return is_quiz, "classic_quiz"
    if row.get("quiz_id") is not None or row.get("quiz_type") is not None:
        return is_quiz, "quiz"
    return is_quiz, ""


def normalize_assignment(row: dict) -> dict:
    """Return the strict URL-free assignment allowlist."""
    if not isinstance(row, dict) or not _id(row.get("id")):
        raise ValueError("assignment row has no stable id")
    is_quiz, quiz_kind = _quiz_classification(row)
    submission_types = row.get("submission_types") if isinstance(row.get("submission_types"), list) else []
    return {
        "id": _id(row.get("id")),
        "name": _normalize_text(row.get("name")),
        "description_text": _description_text(row.get("description")),
        "points_possible": _number(row.get("points_possible")),
        "due_at": _timestamp(row.get("due_at")),
        "unlock_at": _timestamp(row.get("unlock_at")),
        "lock_at": _timestamp(row.get("lock_at")),
        "created_at": _timestamp(row.get("created_at")),
        "updated_at": _timestamp(row.get("updated_at")),
        "published": row.get("published") is True,
        "submission_types": [str(value) for value in submission_types if isinstance(value, str)],
        "assignment_group_id": _id(row.get("assignment_group_id")),
        "quiz_id": _id(row.get("quiz_id")),
        "is_quiz": is_quiz,
        "quiz_kind": quiz_kind,
        "is_quiz_lti_assignment": row.get("is_quiz_lti_assignment") is True,
        "rubric": _normalize_rubric(row.get("rubric")),
        "rubric_settings": _normalize_rubric_settings(row.get("rubric_settings")),
    }


def _normalize_module_item(row: dict) -> dict:
    if not isinstance(row, dict) or not _id(row.get("id")):
        raise ValueError("module item has no stable id")
    return {
        "id": _id(row.get("id")),
        "type": _normalize_text(row.get("type")),
        "title": _normalize_text(row.get("title")),
        "position": _position(row.get("position")),
        "content_id": _id(row.get("content_id")),
    }


def _normalized_items(rows) -> tuple[list[dict], bool]:
    items, dropped = [], False
    for row in rows if isinstance(rows, list) else []:
        try:
            items.append(_normalize_module_item(row))
        except ValueError:
            dropped = True
    items.sort(key=lambda item: (item["position"], item["id"]))
    return items, dropped


def _error_code(error) -> str:
    text = str(error or "").lower()
    if "no canvas token" in text or "no token" in text:
        return "auth_unavailable"
    if "http 401" in text:
        return "auth_failed"
    if "http 403" in text:
        return "forbidden"
    if "http 404" in text:
        return "not_found"
    if "empty" in text:
        return "empty_response"
    return "canvas_unavailable"


def _scope_failure(previous_scope: dict | None, attempted_at: str, error_code: str, *, empty_records):
    previous_records = copy.deepcopy(previous_scope.get("records")) if isinstance(previous_scope, dict) else empty_records
    previous_success_at = str(previous_scope.get("last_success_at") or "") if isinstance(previous_scope, dict) else ""
    has_previous = _valid_iso(previous_success_at)
    return {
        "state": "stale" if has_previous else "unavailable",
        "last_success_at": previous_success_at,
        "last_attempt_at": attempted_at,
        "error_code": error_code,
        "records": previous_records,
    }


def _incomplete_membership(
    previous_scope: dict | None,
    attempted_at: str,
    error_code: str,
    *,
    valid_records,
    empty_records,
) -> dict:
    """Keep last-good membership when a complete list contains invalid rows."""
    previous_success_at = str(previous_scope.get("last_success_at") or "") if isinstance(previous_scope, dict) else ""
    if _valid_iso(previous_success_at):
        return {
            "state": "incomplete",
            "last_success_at": previous_success_at,
            "last_attempt_at": attempted_at,
            "error_code": error_code,
            "records": copy.deepcopy(previous_scope["records"]),
        }
    if not valid_records:
        return _scope_failure(previous_scope, attempted_at, error_code, empty_records=empty_records)
    return {
        "state": "incomplete",
        "last_success_at": "",
        "last_attempt_at": attempted_at,
        "error_code": error_code,
        "records": copy.deepcopy(valid_records),
    }


def _top_level_failure(error, complete, rows, previous_scope: dict | None, attempted_at: str, *, empty_records) -> dict | None:
    if error:
        error_code = str(error).strip()
        if error_code not in {"pagination_incomplete", "invalid_response"}:
            error_code = _error_code(error)
        return _scope_failure(previous_scope, attempted_at, error_code, empty_records=empty_records)
    if complete is not True:
        return _scope_failure(previous_scope, attempted_at, "pagination_incomplete", empty_records=empty_records)
    if not isinstance(rows, list):
        return _scope_failure(previous_scope, attempted_at, "invalid_response", empty_records=empty_records)
    return None


def _acquire_assignments(
    course_id: str,
    canvas_get_all_complete: CanvasGetAllComplete,
    attempted_at: str,
    previous_scope: dict | None,
) -> dict:
    rows, error, complete = acquire_assignment_collection(course_id, canvas_get_all_complete)
    return _assignment_scope_from_receipt(rows, error, complete, attempted_at, previous_scope)


def _assignment_scope_from_receipt(
    rows,
    error,
    complete,
    attempted_at: str,
    previous_scope: dict | None,
) -> dict:
    failure = _top_level_failure(error, complete, rows, previous_scope, attempted_at, empty_records={})
    if failure is not None:
        return failure
    if not rows:
        return {
            "state": "current",
            "last_success_at": attempted_at,
            "last_attempt_at": attempted_at,
            "error_code": "",
            "records": {},
        }
    records = {}
    invalid_membership = False
    for row in rows:
        try:
            record = normalize_assignment(row)
        except ValueError:
            invalid_membership = True
            continue
        if record["id"] in records:
            invalid_membership = True
            continue
        records[record["id"]] = record
    if invalid_membership:
        return _incomplete_membership(
            previous_scope,
            attempted_at,
            "invalid_assignment_record",
            valid_records=records,
            empty_records={},
        )
    return {
        "state": "current",
        "last_success_at": attempted_at,
        "last_attempt_at": attempted_at,
        "error_code": "",
        "records": records,
    }


def normalize_assignment_group(row: dict) -> dict:
    """Return the strict student-free assignment-group allowlist."""
    if not isinstance(row, dict) or not _id(row.get("id")):
        raise ValueError("assignment group has no stable id")
    group_weight = _number(row.get("group_weight"))
    if group_weight is None:
        raise ValueError("assignment group weight is invalid")
    return {
        "id": _id(row.get("id")),
        "name": _normalize_text(row.get("name")),
        "position": _position(row.get("position")),
        "group_weight": group_weight,
    }


def _assignment_group_scope_from_receipt(
    rows,
    error,
    complete,
    attempted_at: str,
    previous_scope: dict | None,
) -> dict:
    failure = _top_level_failure(error, complete, rows, previous_scope, attempted_at, empty_records=[])
    if failure is not None:
        return failure
    if not rows:
        return {
            "state": "current", "last_success_at": attempted_at, "last_attempt_at": attempted_at,
            "error_code": "", "records": [],
        }
    records = []
    seen_ids: set[str] = set()
    invalid_membership = False
    for row in rows:
        try:
            record = normalize_assignment_group(row)
        except ValueError:
            invalid_membership = True
            continue
        if record["id"] in seen_ids:
            invalid_membership = True
            continue
        seen_ids.add(record["id"])
        records.append(record)
    records.sort(key=lambda group: (group["position"], group["id"]))
    if invalid_membership:
        return _incomplete_membership(
            previous_scope, attempted_at, "invalid_assignment_group_record",
            valid_records=records, empty_records=[],
        )
    return {
        "state": "current", "last_success_at": attempted_at, "last_attempt_at": attempted_at,
        "error_code": "", "records": records,
    }


def _acquire_assignment_groups(
    course_id: str,
    canvas_get_all_complete: CanvasGetAllComplete,
    attempted_at: str,
    previous_scope: dict | None,
) -> dict:
    rows, error, complete = canvas_get_all_complete(
        ASSIGNMENT_GROUPS_PATH.format(course_id=course_id), {"per_page": 100},
    )
    return _assignment_group_scope_from_receipt(rows, error, complete, attempted_at, previous_scope)


def _module_previous_by_id(previous_scope: dict | None) -> dict[str, dict]:
    if not isinstance(previous_scope, dict) or not isinstance(previous_scope.get("records"), list):
        return {}
    return {str(record.get("id")): record for record in previous_scope["records"] if isinstance(record, dict)}


def _acquire_modules(
    course_id: str,
    canvas_get_all: CanvasGetAll,
    canvas_get_all_complete: CanvasGetAllComplete,
    attempted_at: str,
    previous_scope: dict | None,
) -> dict:
    rows, error, complete = canvas_get_all_complete(
        MODULES_PATH.format(course_id=course_id),
        {"per_page": 100, "include[]": "items"},
    )
    failure = _top_level_failure(error, complete, rows, previous_scope, attempted_at, empty_records=[])
    if failure is not None:
        return failure
    if not rows:
        return {
            "state": "current",
            "last_success_at": attempted_at,
            "last_attempt_at": attempted_at,
            "error_code": "",
            "records": [],
        }

    valid_rows = []
    seen_module_ids: set[str] = set()
    invalid_membership = False
    for row in rows:
        if not isinstance(row, dict):
            invalid_membership = True
            continue
        module_id = _id(row.get("id"))
        if not module_id or module_id in seen_module_ids:
            invalid_membership = True
            continue
        seen_module_ids.add(module_id)
        valid_rows.append(row)

    previous_by_id = _module_previous_by_id(previous_scope)
    modules: list[dict] = []
    missing_inline: list[tuple[int, str]] = []
    incomplete = False
    for row in valid_rows:
        module = {
            "id": _id(row.get("id")),
            "name": _normalize_text(row.get("name")) or "Untitled module",
            "position": _position(row.get("position")),
            "items": [],
        }
        if "items" in row and isinstance(row.get("items"), list):
            module["items"], dropped = _normalized_items(row.get("items"))
            incomplete = incomplete or dropped
        elif not invalid_membership:
            missing_inline.append((len(modules), module["id"]))
        modules.append(module)

    if invalid_membership:
        modules.sort(key=lambda module: (module["position"], module["id"]))
        return _incomplete_membership(
            previous_scope,
            attempted_at,
            "invalid_module_record",
            valid_records=modules,
            empty_records=[],
        )

    if not modules:
        return _scope_failure(previous_scope, attempted_at, "empty_response", empty_records=[])

    def load_items(index_module_id: tuple[int, str]):
        index, module_id = index_module_id
        items, item_error = canvas_get_all(
            MODULE_ITEMS_PATH.format(course_id=course_id, module_id=module_id),
            {"per_page": 100},
        )
        return index, module_id, items, item_error

    if missing_inline:
        max_workers = min(MODULE_ITEM_CONCURRENCY, len(missing_inline))
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="catalog-module-items") as executor:
            futures = [executor.submit(load_items, target) for target in missing_inline]
            for future in as_completed(futures):
                index, module_id, items, item_error = future.result()
                if item_error or not isinstance(items, list):
                    incomplete = True
                    old = previous_by_id.get(module_id)
                    modules[index]["items"] = copy.deepcopy(old.get("items", [])) if isinstance(old, dict) else []
                    continue
                modules[index]["items"], dropped = _normalized_items(items)
                incomplete = incomplete or dropped

    modules.sort(key=lambda module: (module["position"], module["id"]))
    return {
        "state": "incomplete" if incomplete else "current",
        "last_success_at": attempted_at,
        "last_attempt_at": attempted_at,
        "error_code": "module_items_unavailable" if incomplete else "",
        "records": modules,
    }


def _course_lock(course_id: str) -> threading.RLock:
    with _LOCKS_GUARD:
        return _COURSE_LOCKS.setdefault(str(course_id), threading.RLock())


def _catalog_conflicts(course_id: str, root=None) -> list[Path]:
    directory_value = workspace.course_catalog_dir(course_id, root)
    if not directory_value or not os.path.isdir(directory_value):
        return []
    directory = Path(directory_value)
    excluded = {
        Path(workspace.course_catalog_path(course_id, root)).resolve(),
        Path(workspace.course_catalog_previous_path(course_id, root)).resolve(),
        Path(workspace.course_catalog_v2_path(course_id, root)).resolve(),
        Path(workspace.course_catalog_v2_previous_path(course_id, root)).resolve(),
    }
    return sorted(
        candidate for candidate in directory.glob("*catalog.v*.json")
        if candidate.resolve() not in excluded
    )


def _quarantine(path: Path) -> None:
    if not path.is_file():
        return
    target_dir = path.parent / "quarantine"
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = target_dir / f"{path.name}.{stamp}.corrupt"
    shutil.move(str(path), str(target))


def _read_valid(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            document = json.load(handle)
        validate_catalog(document)
        return copy.deepcopy(document)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        try:
            _quarantine(path)
        except OSError:
            pass
        return None


def read_catalog(course_id: str, *, root=None) -> dict:
    """Read validated v2 then v1 compatibility documents without contacting Canvas."""
    versions = (
        (CATALOG_VERSION, workspace.course_catalog_v2_path, workspace.course_catalog_v2_previous_path),
        (CATALOG_V1_VERSION, workspace.course_catalog_path, workspace.course_catalog_previous_path),
    )
    warnings = ["competing_catalog_files"] if _catalog_conflicts(course_id, root) else []
    if any(not path_fn(course_id, root) for _, *path_fns in versions for path_fn in path_fns):
        return {"catalog": None, "source": "none", "warnings": warnings + ["workspace_not_configured"]}
    for version, canonical_fn, previous_fn in versions:
        canonical_path = Path(canonical_fn(course_id, root))
        previous_path = Path(previous_fn(course_id, root))
        canonical = _read_valid(canonical_path)
        if canonical is not None and canonical["course_id"] == str(course_id):
            return {"catalog": canonical, "source": "canonical", "warnings": warnings}
        if canonical is not None:
            _quarantine(canonical_path)
        previous = _read_valid(previous_path)
        if previous is not None and previous["course_id"] == str(course_id):
            return {"catalog": previous, "source": "previous", "warnings": warnings + ["using_previous_catalog"]}
        if previous is not None:
            _quarantine(previous_path)
    return {"catalog": None, "source": "none", "warnings": warnings}


def _atomic_write(path: Path, document: dict) -> None:
    validate_catalog(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def write_catalog(document: dict, *, root=None) -> dict:
    """Atomically replace v2 canonical while preserving its validated last-good value."""
    validate_catalog(document)
    if document["version"] != CATALOG_VERSION:
        raise ValueError("catalog_v2_required")
    course_id = document["course_id"]
    canonical_value = workspace.course_catalog_v2_path(course_id, root)
    previous_value = workspace.course_catalog_v2_previous_path(course_id, root)
    if not canonical_value or not previous_value:
        raise ValueError("workspace_not_configured")
    canonical_path = Path(canonical_value)
    previous_path = Path(previous_value)
    existing = _read_valid(canonical_path)
    if existing is not None:
        if existing["course_id"] != course_id:
            _quarantine(canonical_path)
        else:
            _atomic_write(previous_path, existing)
    _atomic_write(canonical_path, copy.deepcopy(document))
    return {"catalog": copy.deepcopy(document), "warnings": ["competing_catalog_files"] if _catalog_conflicts(course_id, root) else []}


def refresh_catalog(
    course_id: str,
    course_name: str,
    *,
    canvas_get_all: CanvasGetAll,
    canvas_get_all_complete: CanvasGetAllComplete,
    root=None,
    attempted_at: str | None = None,
    assignment_receipt: AssignmentCollectionReceipt | None = None,
) -> dict:
    """Refresh both scopes, optionally using one already-acquired assignment receipt."""
    course_id = str(course_id or "").strip()
    if not course_id:
        raise ValueError("course_id_required")
    with _course_lock(course_id):
        previous_read = read_catalog(course_id, root=root)
        previous = previous_read.get("catalog")
        timestamp = attempted_at or _now()
        previous_assignments = previous.get("assignments") if isinstance(previous, dict) else None
        previous_modules = previous.get("modules") if isinstance(previous, dict) else None
        previous_groups = previous.get("assignment_groups") if isinstance(previous, dict) and previous.get("version") == CATALOG_VERSION else None
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="course-catalog") as executor:
            module_future = executor.submit(
                _acquire_modules, course_id, canvas_get_all, canvas_get_all_complete, timestamp, previous_modules,
            )
            group_future = executor.submit(
                _acquire_assignment_groups, course_id, canvas_get_all_complete, timestamp, previous_groups,
            )
            if assignment_receipt is None:
                assignment_future = executor.submit(
                    _acquire_assignments, course_id, canvas_get_all_complete, timestamp, previous_assignments,
                )
                assignments = assignment_future.result()
            else:
                rows, error, complete = assignment_receipt
                assignments = _assignment_scope_from_receipt(
                    rows, error, complete, timestamp, previous_assignments,
                )
            modules = module_future.result()
            assignment_groups = group_future.result()
        document = {
            "version": CATALOG_VERSION,
            "course_id": course_id,
            "course_name": _normalize_text(course_name) or course_id,
            "updated_at": timestamp,
            "assignments": assignments,
            "modules": modules,
            "assignment_groups": assignment_groups,
        }
        validate_catalog(document)
        written = write_catalog(document, root=root)
        warnings = sorted(set(previous_read.get("warnings", []) + written.get("warnings", [])))
        return {"catalog": written["catalog"], "source": "canonical", "warnings": warnings}


def refresh_catalog_assignments_only(
    course_id: str,
    *,
    assignment_receipt: AssignmentCollectionReceipt,
    root=None,
    attempted_at: str | None = None,
    course_name: str | None = None,
) -> dict:
    """Coordinated-receipt path for the private mirror's pass-driven callers.

    Applies an already-acquired assignment receipt (no Canvas call of its
    own) to Catalog's assignment scope only. Modules and assignment groups
    are never live-fetched here: they pass through byte-identical to their
    previously-committed value, falling back to the same unavailable/empty-
    records stub this file already uses for a scope with no previous data
    when there is no previous catalog at all (or no previous v2 groups
    scope). The manual ``POST /api/course-catalog/refresh`` route continues
    to use ``refresh_catalog`` for a full three-scope refresh.
    """
    course_id = str(course_id or "").strip()
    if not course_id:
        raise ValueError("course_id_required")
    with _course_lock(course_id):
        previous_read = read_catalog(course_id, root=root)
        previous = previous_read.get("catalog")
        timestamp = attempted_at or _now()
        previous_assignments = previous.get("assignments") if isinstance(previous, dict) else None
        previous_modules = previous.get("modules") if isinstance(previous, dict) else None
        previous_groups = previous.get("assignment_groups") if isinstance(previous, dict) and previous.get("version") == CATALOG_VERSION else None

        rows, error, complete = assignment_receipt
        assignments = _assignment_scope_from_receipt(
            rows, error, complete, timestamp, previous_assignments,
        )
        modules = (
            copy.deepcopy(previous_modules) if previous_modules is not None
            else _scope_failure(None, timestamp, "", empty_records=[])
        )
        assignment_groups = (
            copy.deepcopy(previous_groups) if previous_groups is not None
            else _scope_failure(None, timestamp, "", empty_records=[])
        )

        previous_course_name = previous.get("course_name") if isinstance(previous, dict) else None
        resolved_name = _normalize_text(course_name) or _normalize_text(previous_course_name) or course_id

        document = {
            "version": CATALOG_VERSION,
            "course_id": course_id,
            "course_name": resolved_name,
            "updated_at": timestamp,
            "assignments": assignments,
            "modules": modules,
            "assignment_groups": assignment_groups,
        }
        validate_catalog(document)
        written = write_catalog(document, root=root)
        warnings = sorted(set(previous_read.get("warnings", []) + written.get("warnings", [])))
        return {"catalog": written["catalog"], "source": "canonical", "warnings": warnings}


def public_projection(read_result: dict, *, course_id: str) -> dict:
    """Return PowerGrader-ready data without paths, raw failures, or transport fields."""
    document = read_result.get("catalog") if isinstance(read_result, dict) else None
    if not isinstance(document, dict):
        return {
            "ok": True,
            "available": False,
            "course_id": str(course_id),
            "course_name": "",
            "updated_at": "",
            "source": str(read_result.get("source") or "none") if isinstance(read_result, dict) else "none",
            "warnings": list(read_result.get("warnings") or []) if isinstance(read_result, dict) else [],
            "scopes": {
                "assignments": {"state": "unavailable", "last_success_at": "", "last_attempt_at": "", "error_code": ""},
                "modules": {"state": "unavailable", "last_success_at": "", "last_attempt_at": "", "error_code": ""},
                "assignment_groups": {"state": "unavailable", "last_success_at": "", "last_attempt_at": "", "error_code": ""},
            },
            "assignments": [],
            "modules": [],
            "assignment_groups": [],
        }
    assignments = list(document["assignments"]["records"].values())
    assignments.sort(key=lambda row: row["due_at"] or "0000-00-00", reverse=True)
    modules = []
    for record in document["modules"]["records"]:
        module = copy.deepcopy(record)
        module["assignment_ids"] = [item["content_id"] for item in module["items"] if item["type"].lower() == "assignment" and item["content_id"]]
        module["quiz_ids"] = [item["content_id"] for item in module["items"] if item["type"].lower() == "quiz" and item["content_id"]]
        modules.append(module)
    assignment_groups = copy.deepcopy(document.get("assignment_groups", {}).get("records", []))
    scope_status = {
        name: {key: document[name][key] for key in ("state", "last_success_at", "last_attempt_at", "error_code")}
        for name in ("assignments", "modules")
    }
    if document["version"] == CATALOG_VERSION:
        scope_status["assignment_groups"] = {
            key: document["assignment_groups"][key]
            for key in ("state", "last_success_at", "last_attempt_at", "error_code")
        }
    else:
        scope_status["assignment_groups"] = {
            "state": "unavailable", "last_success_at": "", "last_attempt_at": "", "error_code": "",
        }
    return {
        "ok": True,
        "available": bool(assignments or modules or assignment_groups),
        "course_id": document["course_id"],
        "course_name": document["course_name"],
        "updated_at": document["updated_at"],
        "source": str(read_result.get("source") or "canonical"),
        "warnings": list(read_result.get("warnings") or []),
        "scopes": scope_status,
        "assignments": assignments,
        "modules": modules,
        "assignment_groups": assignment_groups,
    }
