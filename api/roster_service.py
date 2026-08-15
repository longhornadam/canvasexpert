"""Shared roster fetch, section, and vault-upsert use cases."""
from __future__ import annotations

from collections.abc import Callable


def fetch_students(course_id: str, *, canvas_get_all=None) -> tuple[list[dict] | None, str | None]:
    if canvas_get_all is None:
        from api.platform_services.canvas_client import canvas_get_all as default_canvas_get_all
        canvas_get_all = default_canvas_get_all
    return canvas_get_all(
        f"/api/v1/courses/{course_id}/users",
        {"enrollment_type[]": ["student"], "include[]": ["enrollments"], "per_page": 100},
    )


def fetch_sections(course_id: str, *, canvas_get_all=None) -> dict[str, str]:
    if canvas_get_all is None:
        from api.platform_services.canvas_client import canvas_get_all as default_canvas_get_all
        canvas_get_all = default_canvas_get_all
    sections, error = canvas_get_all(
        f"/api/v1/courses/{course_id}/sections", {"per_page": 100}
    )
    if error or not sections:
        return {}
    return {str(section["id"]): section.get("name", f"Section {section['id']}")
            for section in sections}


def upsert_roster(vault, users: list[dict]) -> None:
    """Mutation-only roster upsert; persistence belongs to the caller."""
    remember_identity = getattr(vault, "remember_identity", None)
    if remember_identity is not None:
        # Populate the shared identity set first. Assignment then sees the
        # complete vault-derived collision set, independent of API row order.
        for user in users or []:
            canvas_id = str(user.get("id", ""))
            if not canvas_id:
                continue
            name = user.get("name") or user.get("sortable_name") or ""
            remember_identity(canvas_id, name, str(user.get("sis_user_id") or ""))

    roster_tokens: set = set()
    for user in users or []:
        for source in (user.get("name"), user.get("sortable_name"), user.get("short_name")):
            for token in (source or "").split():
                roster_tokens.add(token.lower())

    for user in users or []:
        canvas_id = str(user.get("id", ""))
        if not canvas_id:
            continue
        name = user.get("name") or user.get("sortable_name") or ""
        sis_id = str(user.get("sis_user_id") or "")
        vault.get_or_assign(canvas_id, name, sis_id, roster_names=roster_tokens)
        short_name = (user.get("short_name") or "").strip()
        name_tokens = {token.lower() for token in name.split()}
        if (short_name and short_name.lower() != name.lower()
                and short_name.lower() not in name_tokens):
            vault.add_nicknames(canvas_id, [short_name])


def sync_roster_for_course(
    vault,
    course_id: str,
    *,
    canvas_get_all=None,
    fetch_students_override: Callable[[str], tuple[list[dict] | None, str | None]] | None = None,
) -> tuple[list[dict] | None, str | None]:
    """Fetch first, then transactionally upsert one course roster."""
    fetch = fetch_students_override or (lambda cid: fetch_students(cid, canvas_get_all=canvas_get_all))
    users, error = fetch(course_id)
    if error:
        return None, error
    transaction = getattr(vault, "transaction", None)
    if transaction is None:
        upsert_roster(vault, users)
    else:
        with transaction():
            upsert_roster(vault, users)
    return users, None
