"""Assistant-facing staged-content push use case.

This is the shared non-HTTP boundary used by MCP, and it mirrors
``api/sis_grade_bridge.py``: live Canvas behavior stays inside the Operation
Ledger adapters, while this module resolves one staged draft, freezes one
operation against one Current course, and shapes only course-only results.

The teacher's own push tabs stay exactly as they are. Both routes prepare the
same adapter payload, freeze the same batch, and apply through the same
executor, so a draft landed from the chat and a draft landed from the web UI
are the same write with the same drift checks, claims, and receipts.

The draft must already be staged in the per-kind To Review Inbox
(``runtime_paths.inbox_folder``). Only a draft's label crosses this boundary,
never an absolute path: the assistant names what it staged, and this module
resolves that label against the marker-gated listing.
"""

from __future__ import annotations

from api.operation_ledger import batches, executor, models, operations, registry
from api.operation_ledger.adapters.assignment import KIND as ASSIGNMENT_KIND
from api.operation_ledger.adapters.page import KIND as PAGE_KIND
from api.operation_ledger.adapters.quiz import KIND as QUIZ_KIND
from api.operation_ledger.adapters.rubric import KIND as RUBRIC_KIND
from api.platform_services import config
from api.webui import deps

# Teacher-facing kind -> ledger operation kind. These are the four kinds that
# have an Inbox, an authoring contract, and a push tab; they stay in step with
# ``mcp_server.tools._STAGED_CONTRACT_KINDS``.
_LEDGER_KINDS = {
    "quiz": QUIZ_KIND,
    "assignment": ASSIGNMENT_KIND,
    "page": PAGE_KIND,
    "rubric": RUBRIC_KIND,
}

# Delivery options each kind can actually carry. Naming one a kind does not
# accept is refused rather than dropped: a teacher who says "due Friday" about
# a page should hear that pages have no due date, not watch it vanish.
_SCHEDULE_OPTIONS = ("due_at", "unlock_at", "lock_at")
_KIND_OPTIONS = {
    "quiz": ("published", "module_name", "assignment_group_name",
             "post_to_sis", *_SCHEDULE_OPTIONS),
    "assignment": ("published", "module_name", "assignment_group_name",
                   "post_to_sis", *_SCHEDULE_OPTIONS),
    "page": ("published", "module_name"),
    "rubric": ("published",),
}

_TEXT_OPTIONS = ("module_name", "assignment_group_name", *_SCHEDULE_OPTIONS)
_FLAG_OPTIONS = ("published", "post_to_sis")


def _current_course(course_id: str) -> bool:
    wanted = str(course_id or "").strip()
    return bool(wanted) and wanted in {
        str(course.get("id") or "").strip()
        for course in config.active_courses()
    }


def _kind_error(kind: str) -> str:
    return (f"unknown kind '{kind}'; expected one of: "
            f"{', '.join(_LEDGER_KINDS)}")


def _resolve_staged_draft(kind: str, label: str) -> tuple[str | None, str | None]:
    """Return ``(path, None)`` for one staged label, or ``(None, error)``.

    Matches the exact label first, then case-insensitively, then with ``.txt``
    appended, so an assistant that named the draft without its extension still
    resolves. An ambiguous label is refused rather than guessed at.
    """
    wanted = str(label or "").strip()
    if not wanted:
        return None, "label is required; call list_staged_content for the staged labels"
    entries = deps.list_inbox_files(kind)
    if not entries:
        return None, (
            f"no {kind} draft is staged for review; stage the draft first "
            "(see get_authoring_contract) and then push it"
        )

    for candidates in (
        [entry for entry in entries if entry["label"] == wanted],
        [entry for entry in entries if entry["label"].casefold() == wanted.casefold()],
        [entry for entry in entries
         if entry["label"].casefold() == f"{wanted}.txt".casefold()],
    ):
        if len(candidates) == 1:
            return candidates[0]["path"], None
        if len(candidates) > 1:
            return None, (
                f"'{wanted}' matches more than one staged {kind} draft; "
                "use the exact label from list_staged_content"
            )

    known = ", ".join(entry["label"] for entry in entries)
    return None, (
        f"no staged {kind} draft is labeled '{wanted}'; staged {kind} drafts "
        f"are: {known}"
    )


def _collect_options(kind: str, options: dict) -> tuple[dict, str | None]:
    """Normalize the delivery options, refusing any this kind cannot carry."""
    named = {}
    for key in _FLAG_OPTIONS:
        if bool(options.get(key)):
            named[key] = True
    for key in _TEXT_OPTIONS:
        value = str(options.get(key) or "").strip()
        if value:
            named[key] = value

    allowed = _KIND_OPTIONS[kind]
    unsupported = sorted(key for key in named if key not in allowed)
    if unsupported:
        return {}, (
            f"a {kind} push does not take {', '.join(unsupported)}; "
            f"it takes {', '.join(allowed)}"
        )
    # published is always meaningful, and always explicit in the payload.
    named["published"] = bool(options.get("published"))
    return named, None


def _prepare_request(kind: str, path: str, named: dict) -> dict:
    """Build the adapter's prepare request from one resolved draft and options.

    A quiz carries its options as QuizForge push settings rather than as
    top-level fields; ``qf_pusher.SETTING_KEYS`` covers every one of them and
    drops anything it does not recognize.
    """
    if kind == "quiz":
        return {"mode": "whole", "path": path, "settings": dict(named)}
    return {"path": path, **named}


def preview_content_push(
    course_id: str,
    kind: str,
    label: str,
    *,
    published: bool = False,
    module_name: str = "",
    assignment_group_name: str = "",
    due_at: str = "",
    unlock_at: str = "",
    lock_at: str = "",
    post_to_sis: bool = False,
) -> dict:
    """Freeze one staged draft into a persisted, digest-protected review.

    Makes no Canvas write. Reads Canvas only to capture the baseline the apply
    step drift-checks against, exactly as the push tab's prepare step does.
    """
    course_key = str(course_id or "").strip()
    content_kind = str(kind or "").strip()
    if content_kind not in _LEDGER_KINDS:
        return {"ok": False, "error": _kind_error(content_kind)}
    if not course_key:
        return {"ok": False, "error": "course_id is required"}
    if not _current_course(course_key):
        return {"ok": False, "error": "course is not in Current courses"}

    named, option_error = _collect_options(content_kind, {
        "published": published,
        "module_name": module_name,
        "assignment_group_name": assignment_group_name,
        "due_at": due_at,
        "unlock_at": unlock_at,
        "lock_at": lock_at,
        "post_to_sis": post_to_sis,
    })
    if option_error:
        return {"ok": False, "error": option_error}

    path, resolve_error = _resolve_staged_draft(content_kind, label)
    if resolve_error:
        return {"ok": False, "error": resolve_error}

    ledger_kind = _LEDGER_KINDS[content_kind]
    adapter = registry.get_adapter(ledger_kind)
    try:
        payload = adapter.build_payload(_prepare_request(content_kind, path, named))
        target = adapter.verify_targets(payload, [{"course_id": course_key}])[0]
        baseline = adapter.capture_baseline(payload, target)
        target_record = models.new_target(
            target_key=target["target_key"],
            idempotency_key=target["idempotency_key"],
            course_id=target["course_id"],
            baseline=baseline,
        )
        operation_id = models.new_operation_id()
        operation = models.new_operation(
            operation_id=operation_id,
            kind=ledger_kind,
            source_ref={"type": "staged_inbox", "value": content_kind},
            source_digest=adapter.source_digest(payload),
            normalized_payload=payload,
            targets=[target_record],
        )
        operations.create_operation(operation)
        frozen = adapter.freeze_review(payload, target_record, baseline)
        batch = batches.freeze_batch([operation_id], {operation_id: [frozen]})
        operations.set_operation_review(operation_id, batch)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "blocking": True}
    except Exception:
        return {"ok": False, "error": f"the {content_kind} push could not be prepared"}

    return {
        "ok": True,
        "kind": content_kind,
        "label": label,
        "operation_id": operation_id,
        "batch_id": batch["batch_id"],
        "review_digest": batch["review_digest"],
        "preview": _scrub_paths(frozen),
    }


def apply_content_push(
    operation_id: str, batch_id: str, review_digest: str
) -> dict:
    """Write exactly the frozen staged-content review to Canvas."""
    operation_key = str(operation_id or "").strip()
    batch_key = str(batch_id or "").strip()
    digest = str(review_digest or "").strip()
    if not operation_key or not batch_key or not digest:
        return {
            "ok": False,
            "error": "operation_id, batch_id, and review_digest are required",
        }
    operation = operations.get_operation(operation_key)
    if operation is None or operation.get("kind") not in set(_LEDGER_KINDS.values()):
        return {"ok": False, "error": "content push operation was not found"}
    try:
        result = executor.apply_operation(operation_key, batch_key, digest)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:
        return {"ok": False, "error": "the content push could not complete"}

    return _result_projection(operation, result)


def _content_kind(ledger_kind: str) -> str:
    for name, value in _LEDGER_KINDS.items():
        if value == ledger_kind:
            return name
    return ledger_kind


def _result_projection(operation: dict, result: dict) -> dict:
    """Course-only outcome: what landed, where, and what needs attention.

    ``target_key`` and the private diagnostics stay out; the Canvas URL of the
    created object stays in, because that is the one thing the teacher wants
    from a push they asked for in chat.
    """
    targets = []
    for target in result.get("target_results") or []:
        row = {"state": target.get("state")}
        if target.get("returned_object_url"):
            row["url"] = target["returned_object_url"]
        if target.get("error_code"):
            row["error_code"] = target["error_code"]
        steps = [
            {"step": step.get("step_key"), "state": step.get("state"),
             "error_code": step.get("error_code")}
            for step in target.get("steps") or []
            if step.get("state") not in (None, "applied")
        ]
        if steps:
            row["unfinished_steps"] = steps
        targets.append(row)

    return {
        "ok": bool(result.get("ok")),
        "kind": _content_kind(operation.get("kind", "")),
        "operation_id": result.get("operation_id"),
        "status": result.get("status"),
        "targets": targets,
    }


def _scrub_paths(value):
    """Drop any local filesystem path a frozen review carries.

    No option this boundary accepts sets one today (printable attachments are
    web-UI only), so this is a guard against a future adapter field, not a
    known leak.
    """
    if isinstance(value, dict):
        return {key: _scrub_paths(item) for key, item in value.items()
                if not str(key).endswith("path")}
    if isinstance(value, list):
        return [_scrub_paths(item) for item in value]
    return value


__all__ = [
    "apply_content_push",
    "preview_content_push",
]
