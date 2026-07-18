"""Mirror-backed reads implementing the ``gradebook_queries`` interface.

Same five functions, same ``(data, error)`` tuple contract, but served from
the CanvasMirror store instead of live Canvas — a read costs milliseconds and
works offline. Consumers decide *whether* to serve from the mirror via the
freshness helpers here: a collection older than the serve threshold (config
``mirror_serve_max_age_hours``, default 6 h) is not served, and callers fall
back to live Canvas — always labeling results with ``source`` + ``synced_at``
so staleness is visible, never silent (design law #4).
"""
from __future__ import annotations

from types import SimpleNamespace

from . import store

MIRROR_UNAVAILABLE = "mirror unavailable for this course"


def _serve_max_age_hours() -> float:
    try:
        from api.webui import config
        return config.mirror_serve_max_age_hours()
    except Exception:
        return 6.0


def _fresh(synced_at: str, max_age_hours: float | None, now: str | None) -> str:
    limit = max_age_hours if max_age_hours is not None else _serve_max_age_hours()
    age = store.age_hours(synced_at, now)
    return synced_at if age is not None and age < limit else ""


def data_freshness(course_id, *, root=None, max_age_hours=None, now=None) -> str:
    """``synced_at`` of the newest successful data pass (full or delta) when
    within the serve threshold, else ''. ISO-Z strings compare lexically."""
    passes = store.read_sync(course_id, root=root)["passes"]
    synced_at = max(passes["full"]["last_success_at"],
                    passes["delta"]["last_success_at"])
    return _fresh(synced_at, max_age_hours, now)


def roster_freshness(course_id, *, root=None, max_age_hours=None, now=None) -> str:
    passes = store.read_sync(course_id, root=root)["passes"]
    synced_at = max(passes["roster"]["last_success_at"],
                    passes["full"]["last_success_at"])
    return _fresh(synced_at, max_age_hours, now)


# --- the gradebook_queries interface, mirror-backed ---------------------------

def course_students(course_id, *, root=None):
    document = store.read_roster(course_id, root=root)
    if document is None:
        return None, MIRROR_UNAVAILABLE
    return list(document["students"].values()), None


def course_assignments(course_id, *, root=None):
    document = store.read_assignments(course_id, root=root)
    if document is None:
        return None, MIRROR_UNAVAILABLE
    return list(document["assignments"].values()), None


def course_submissions(course_id, *, root=None):
    """Enumerate submission files, then drop any ``assignment_id`` not
    present in the committed assignment index (1.0beta slice 01b, locked
    design item 1) — deletion is invisible to this read the moment the next
    delta commits a smaller index, without waiting for orphan files to be
    pruned from disk. A missing/corrupt index already returns unavailable
    above (last-good rules unchanged); filtering only ever narrows the
    directory listing, never invents rows for ids the index doesn't have."""
    assignments = store.read_assignments(course_id, root=root)
    if assignments is None:
        return None, MIRROR_UNAVAILABLE
    valid_ids = set(assignments["assignments"])
    rows = []
    for assignment_id in store.list_submission_assignment_ids(course_id, root=root):
        if assignment_id not in valid_ids:
            continue
        document = store.read_submissions(course_id, assignment_id, root=root)
        if document is None:
            continue
        rows.extend(entry["current"]
                    for _, entry in sorted(document["submissions"].items()))
    return rows, None


def assignment(course_id, assignment_id, *, root=None):
    document = store.read_assignments(course_id, root=root)
    row = (document or {}).get("assignments", {}).get(str(assignment_id))
    if row is None:
        return None, MIRROR_UNAVAILABLE
    return row, None


def assignment_submissions(course_id, assignment_id, *, root=None):
    """Same membership filtering as ``course_submissions`` (item 1), applied
    to a single assignment: a missing/corrupt assignment index behaves as
    today (last-good rules — the index simply doesn't gate this read), but a
    present index that no longer lists ``assignment_id`` reports unavailable
    even if an orphan submission file is still on disk."""
    assignments = store.read_assignments(course_id, root=root)
    if assignments is not None and str(assignment_id) not in assignments["assignments"]:
        return None, MIRROR_UNAVAILABLE
    document = store.read_submissions(course_id, assignment_id, root=root)
    if document is None:
        return None, MIRROR_UNAVAILABLE
    return [entry["current"]
            for _, entry in sorted(document["submissions"].items())], None


def snapshot_queries(course_id, *, root=None, max_age_hours=None, now=None):
    """``(queries_namespace, synced_at)`` when the mirror can serve the whole
    gradebook snapshot, else ``(None, "")``. The namespace is a drop-in for
    ``gradebook_snapshot.load_snapshot(queries=...)``."""
    synced_at = data_freshness(course_id, root=root,
                               max_age_hours=max_age_hours, now=now)
    if not synced_at:
        return None, ""
    if (store.read_roster(course_id, root=root) is None
            or store.read_assignments(course_id, root=root) is None):
        return None, ""
    namespace = SimpleNamespace(
        course_students=lambda cid: course_students(cid, root=root),
        course_assignments=lambda cid: course_assignments(cid, root=root),
        course_submissions=lambda cid: course_submissions(cid, root=root),
    )
    return namespace, synced_at
