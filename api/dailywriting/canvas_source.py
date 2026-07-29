"""Map stored Canvas assignment facts to Writing Record context."""
from __future__ import annotations

from datetime import date as date_cls, datetime

from api.dailywriting.core.models import AssignmentContext


class DateDerivationError(ValueError):
    """An assignment has no reliable date for the writing record."""


def _parse_date(value) -> date_cls | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def rep_date(assignment: dict) -> date_cls:
    """Use due date, then unlock date, then creation date; never invent one."""
    for key in ("due_at", "unlock_at", "created_at"):
        if parsed := _parse_date(assignment.get(key)):
            return parsed
    raise DateDerivationError(f"assignment {assignment.get('id')!r} has no due_at, unlock_at, or created_at to derive a record date from")


def rep_id_for(course_id: str, assignment_id: str) -> str:
    """Stable replacement key for one selected Canvas assignment."""
    return f"canvas:{course_id}:{assignment_id}"


def submission_id_for(course_id: str, assignment_id: str, canvas_user_id) -> str:
    """Stable replacement key for a student's current assignment submission."""
    return f"canvas:{course_id}:{assignment_id}:{canvas_user_id}"


def assignment_context(assignment: dict, *, rep_id: str) -> AssignmentContext:
    """Keep supplied catalog facts and leave unknown assignment meaning unknown."""
    return AssignmentContext(rep_id=rep_id, date=rep_date(assignment), prompt_text=assignment.get("description_text") or "", scaffold_blocks=[], source_texts=[], word_cap=None, section_id=None)
