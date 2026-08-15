"""Canonical reviewed Learning Objectives storage and exact preview service.

This module owns the only objective document. It knows the shape and source
digest rules; MCP owns the Current-course gate and exposes only preview/apply.
Glass uses the same source-resolution helpers but never mutates the file.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from datetime import date, datetime, timezone

from api.platform_services import workspace


VERSION = 2
ROOT_KEYS = {"version", "revision", "objectives"}
ENTRY_KEYS = {
    "id", "objective", "effective_start", "effective_end", "source_refs",
    "source_digest", "catalog_updated_at", "authored_at",
}
SOURCE_REF_KEYS = {"kind", "id", "title"}
SOURCE_KINDS = frozenset({"module", "assignment", "page"})
HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_STORE_LOCK = threading.RLock()


class CatalogNeedsAttentionError(ValueError):
    """The local Catalog is stale, unavailable, or structurally unusable."""


class ChangedSourceError(ValueError):
    """A referenced Catalog record is missing or no longer matches its digest."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _normalize_text(value) -> str:
    text = "" if value is None else str(value)
    if "<" in text or ">" in text:
        raise ValueError("objective text must be plain text")
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise ValueError("objective text contains control characters")
    return " ".join(text.split())


def _iso_date(value, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO date") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{label} must be an ISO date")
    return value


def _iso_timestamp(value, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be an ISO timestamp")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO timestamp") from error
    return value


def normalize_objective(value) -> str:
    text = _normalize_text(value)
    if not 1 <= len(text) <= 500:
        raise ValueError("objective must be 1-500 characters after whitespace normalization")
    return text


def normalize_source_refs(value) -> list[dict]:
    if not isinstance(value, list) or not value:
        raise ValueError("source_refs must be a non-empty list")
    refs = []
    seen = set()
    for ref in value:
        if not isinstance(ref, dict) or set(ref) != SOURCE_REF_KEYS:
            raise ValueError("source ref schema is invalid")
        kind = ref.get("kind")
        ident = ref.get("id")
        title = _normalize_text(ref.get("title"))
        if kind not in SOURCE_KINDS or not isinstance(ident, str) or not ident.strip() or not title:
            raise ValueError("source ref is invalid")
        key = (kind, ident.strip())
        if key in seen:
            raise ValueError("source refs must be unique")
        seen.add(key)
        refs.append({"kind": kind, "id": ident.strip(), "title": title})
    return refs


def normalize_entry(entry: dict) -> dict:
    if not isinstance(entry, dict) or set(entry) != ENTRY_KEYS:
        raise ValueError("objective entry schema is invalid")
    ident = entry["id"]
    if not isinstance(ident, str) or not ident.strip() or len(ident) > 128:
        raise ValueError("objective id is invalid")
    objective = normalize_objective(entry["objective"])
    start = _iso_date(entry["effective_start"], "effective_start")
    end = _iso_date(entry["effective_end"], "effective_end")
    if start > end:
        raise ValueError("effective date range is reversed")
    refs = normalize_source_refs(entry["source_refs"])
    digest = entry["source_digest"]
    if not isinstance(digest, str) or not HEX_DIGEST.fullmatch(digest):
        raise ValueError("source_digest must be a sha256 hex digest")
    return {
        "id": ident.strip(),
        "objective": objective,
        "effective_start": start,
        "effective_end": end,
        "source_refs": refs,
        "source_digest": digest,
        "catalog_updated_at": _iso_timestamp(entry["catalog_updated_at"], "catalog_updated_at"),
        "authored_at": _iso_timestamp(entry["authored_at"], "authored_at"),
    }


def _ranges_overlap(left: dict, right: dict) -> bool:
    return left["effective_start"] <= right["effective_end"] and right["effective_start"] <= left["effective_end"]


def validate_document(document: dict) -> dict:
    if not isinstance(document, dict) or set(document) != ROOT_KEYS:
        raise ValueError("objective document schema is invalid")
    if document["version"] != VERSION or not isinstance(document["revision"], int) or isinstance(document["revision"], bool) or document["revision"] < 0:
        raise ValueError("objective document version or revision is invalid")
    objectives = document["objectives"]
    if not isinstance(objectives, dict):
        raise ValueError("objectives must be an object")
    for course_id, entries in objectives.items():
        if not isinstance(course_id, str) or not course_id.strip() or not isinstance(entries, list):
            raise ValueError("objective course bucket is invalid")
        normalized = [normalize_entry(entry) for entry in entries]
        ids = [entry["id"] for entry in normalized]
        if len(ids) != len(set(ids)):
            raise ValueError("objective ids must be unique within a course")
        for index, entry in enumerate(normalized):
            if any(_ranges_overlap(entry, other) for other in normalized[index + 1:]):
                raise ValueError("objective date ranges overlap")
    return document


def empty_document() -> dict:
    return {"version": VERSION, "revision": 0, "objectives": {}}


def read_document(*, root=None) -> dict:
    path = workspace.learning_objectives_path(root)
    if not path or not os.path.isfile(workspace.extended_path(path)):
        return empty_document()
    try:
        with open(workspace.extended_path(path), encoding="utf-8") as handle:
            document = json.load(handle)
        validate_document(document)
        return copy.deepcopy(document)
    except json.JSONDecodeError as error:
        raise ValueError("objective_document_invalid") from error
    except (OSError, TypeError, ValueError) as error:
        raise ValueError("objective_document_invalid") from error


def _atomic_write(document: dict, *, root=None) -> dict:
    validate_document(document)
    path = workspace.learning_objectives_path(root)
    if not path:
        raise ValueError("workspace_not_configured")
    directory = workspace.extended_path(os.path.dirname(path))
    os.makedirs(directory, exist_ok=True)
    payload = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=".Learning Objectives-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, workspace.extended_path(path))
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return copy.deepcopy(document)


def source_records(catalog: dict, source_refs: list[dict]) -> list[dict]:
    if not isinstance(catalog, dict) or catalog.get("version") != 3:
        raise CatalogNeedsAttentionError("catalog_v3_required")
    collections = {
        "module": catalog.get("modules", {}).get("records", []),
        "assignment": catalog.get("assignments", {}).get("records", {}),
        "page": catalog.get("pages", {}).get("records", []),
    }
    records = []
    for ref in source_refs:
        scope_key = {"module": "modules", "assignment": "assignments", "page": "pages"}[ref["kind"]]
        scope = catalog.get(scope_key)
        if not isinstance(scope, dict) or scope.get("state") != "current":
            raise CatalogNeedsAttentionError("catalog source scope is not current")
        collection = collections[ref["kind"]]
        record = collection.get(ref["id"]) if isinstance(collection, dict) else next(
            (item for item in collection if isinstance(item, dict) and str(item.get("id")) == ref["id"]), None)
        if not isinstance(record, dict):
            raise ChangedSourceError("source ref does not resolve")
        if ref["kind"] == "page" and record.get("published") is not True:
            raise ChangedSourceError("source ref page is not published")
        title_key = "name" if ref["kind"] in {"module", "assignment"} else "title"
        if _normalize_text(record.get(title_key)) != ref["title"]:
            raise ChangedSourceError("source ref title does not match catalog")
        records.append(copy.deepcopy(record))
    return records


def source_digest(catalog: dict, source_refs: list[dict]) -> str:
    return hashlib.sha256(_canonical(source_records(catalog, source_refs))).hexdigest()


def preview_digest(preview: dict) -> str:
    return hashlib.sha256(_canonical(preview)).hexdigest()


def build_preview(*, course_id: str, catalog: dict, document: dict, objective,
                  effective_start, effective_end, source_refs, replaces=None) -> dict:
    normalized_refs = normalize_source_refs(source_refs)
    normalized_objective = normalize_objective(objective)
    start = _iso_date(effective_start, "effective_start")
    end = _iso_date(effective_end, "effective_end")
    if start > end:
        raise ValueError("effective date range is reversed")
    digest = source_digest(catalog, normalized_refs)
    proposed = {
        "objective": normalized_objective,
        "effective_start": start,
        "effective_end": end,
        "source_refs": normalized_refs,
        "source_digest": digest,
        "catalog_updated_at": str(catalog["updated_at"]),
        "authored_at": _now(),
    }
    normalized_document = copy.deepcopy(document)
    validate_document(normalized_document)
    entries = normalized_document["objectives"].setdefault(str(course_id), [])
    outgoing = None
    if replaces is not None:
        if not isinstance(replaces, str) or not replaces.strip():
            raise ValueError("replaces must be an objective id")
        outgoing = next((entry for entry in entries if entry["id"] == replaces), None)
        if outgoing is None:
            raise ValueError("objective id not found")
    proposed["id"] = outgoing["id"] if outgoing else uuid.uuid4().hex
    for existing in entries:
        if outgoing is not None and existing["id"] == outgoing["id"]:
            continue
        if _ranges_overlap(proposed, existing):
            raise ValueError("objective date ranges overlap")
    preview = {
        "course_id": str(course_id),
        "catalog_generation": f"catalog:v3:{catalog['updated_at']}",
        "catalog_updated_at": str(catalog["updated_at"]),
        "document_revision": normalized_document["revision"],
        "source_digest": digest,
        "source_titles": [ref["title"] for ref in normalized_refs],
        "replaces": outgoing["id"] if outgoing else None,
        "outgoing": outgoing["objective"] if outgoing else None,
        "incoming": proposed["objective"],
        "proposed": proposed,
    }
    return {"preview": preview, "preview_digest": preview_digest(preview),
            "current_revision": normalized_document["revision"]}


def apply_preview(*, course_id: str, preview: dict, preview_digest_value: str,
                  expected_revision: int, catalog: dict, document: dict,
                  root=None) -> dict:
    with _STORE_LOCK:
        if not isinstance(preview, dict) or preview_digest(preview) != preview_digest_value:
            raise ValueError("preview_digest_mismatch")
        if preview.get("course_id") != str(course_id):
            raise ValueError("preview_course_mismatch")
        current = read_document(root=root)
        if (preview.get("document_revision") != expected_revision
                or document.get("revision") != expected_revision
                or current.get("revision") != expected_revision):
            raise ValueError("objective_revision_mismatch")
        if preview.get("catalog_generation") != f"catalog:v3:{catalog.get('updated_at')}":
            raise ValueError("catalog_changed")
        proposed = preview.get("proposed")
        if not isinstance(proposed, dict):
            raise ValueError("preview_proposed_record_missing")
        proposed = normalize_entry(proposed)
        if proposed["catalog_updated_at"] != str(catalog.get("updated_at")):
            raise ValueError("catalog_changed")
        if proposed["source_digest"] != source_digest(catalog, proposed["source_refs"]):
            raise ValueError("source_changed")
        validate_document(current)
        entries = current["objectives"].setdefault(str(course_id), [])
        replaces = preview.get("replaces")
        if replaces is not None:
            if proposed["id"] != replaces:
                raise ValueError("objective replacement id mismatch")
            index = next((i for i, entry in enumerate(entries) if entry["id"] == replaces), None)
            if index is None:
                raise ValueError("objective id not found")
            if any(_ranges_overlap(proposed, existing) for i, existing in enumerate(entries) if i != index):
                raise ValueError("objective date ranges overlap")
            entries[index] = proposed
        else:
            if any(_ranges_overlap(proposed, existing) for existing in entries):
                raise ValueError("objective date ranges overlap")
            if any(existing["id"] == proposed["id"] for existing in entries):
                raise ValueError("objective id already exists")
            entries.append(proposed)
        current["revision"] += 1
        return _atomic_write(current, root=root)


def delete_entry(*, course_id: str, entry_id: str, expected_revision: int, root=None) -> dict:
    with _STORE_LOCK:
        current = read_document(root=root)
        if current.get("revision") != expected_revision:
            raise ValueError("objective_revision_mismatch")
        entries = current["objectives"].get(str(course_id))
        if entries is None or not any(entry.get("id") == entry_id for entry in entries):
            raise ValueError("objective id not found")
        current["objectives"][str(course_id)] = [entry for entry in entries if entry.get("id") != entry_id]
        current["revision"] += 1
        return _atomic_write(current, root=root)
