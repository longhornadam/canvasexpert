"""Who may see a fact: the classroom wall, or only the teacher.

The split this module encodes is *not* "student data versus not". Schools put
birthdays and full names on signage outside the building and announce
outstanding achievements over the intercom. The real line is whether a fact is
classroom-facing or teacher-facing, and the teacher owns where it falls.

So this module is deliberately narrow. It is a lookup, not a judgement. It does
not reason about FERPA, it does not infer, and it never decides that something
is restricted on its own: a kind is teacher-facing because it is on the list
below, or because the teacher said so. Everything else is assumed opt-in. Where
there is doubt, the surface asks the teacher and defers -- that conversation
belongs in the UI, not in here.

`docs/contracts/classroom-facing-data-contract.md` is the authority for the two
lists; this file is the enforcement. Per `docs/reference/project-state.md`, a
model instruction is not an enforcement boundary, which is why the filter is
code and every emitted item has to carry an audience.

Pure by design: no route, config, Canvas, vault, or clock imports, exactly the
posture `api/roster_context.py` documents. That is what makes the whole policy
testable without app state.
"""
from __future__ import annotations

CLASSROOM = "classroom"
TEACHER = "teacher"

# The floor a numeric score has to clear before it can be shown to the room.
# 90% is "an A", 4 out of 5 on a five-point rubric. Below it, a score is
# teacher-facing, full stop.
#
# Nothing in the public day-context slice applies this to a real score -- the
# private sources that carry scores arrive in a later batch. It lives here now
# because the contract document states the same number, and one source of truth
# for it beats discovering two later.
SCORE_FLOOR_PERCENT = 90

# Facts a classroom screen may show.
#
# Grouped by where they come from rather than alphabetically, because the groups
# are how a reader checks the list against the contract document.
CLASSROOM_FACING = frozenset({
    # The shape of the school day.
    "bell_schedule", "day_type", "block",
    # The district academic calendar.
    "no_school", "grading_period_end", "report_card",
    # School events the teacher records.
    "game", "dance", "assembly", "performance", "spirit",
    "tutorial", "club", "library", "other",
    # Names, and per-student facts a school announces publicly.
    "student_name", "teacher_name",
    "birthday", "achievement", "missing_work", "staar_masters",
    # A teacher-reviewed, student-free classroom objective.
    "learning_objective",
})

# Facts that stay with the teacher. Of these, the Special Ed and 504
# designations are the ones that actually generate challenges and lawsuits, so
# they are the least negotiable entries on the list.
TEACHER_FACING = frozenset({
    "score_below_floor", "behavior", "special_ed", "section_504",
    "ssn", "address", "phone", "parent_email", "student_id",
    "economic_status", "staar_below_masters",
})


def audience_for(kind: object) -> str | None:
    """`CLASSROOM`, `TEACHER`, or None when the kind is not in the vocabulary.

    None is not "safe". It means nobody has classified this yet, and callers
    are expected to treat it the way `classroom_safe` does.
    """
    if not isinstance(kind, str):
        return None
    if kind in CLASSROOM_FACING:
        return CLASSROOM
    if kind in TEACHER_FACING:
        return TEACHER
    return None


def classroom_safe(item: object) -> bool:
    """True when this item may be handed to a classroom-facing surface.

    Fails closed on an unrecognised kind. An unknown kind is not a
    classroom-facing kind that happens to be missing from the list -- it is a
    fact nobody has classified, and guessing in the permissive direction is how
    something ends up on a wall that should not be.
    """
    if not isinstance(item, dict):
        return False
    return audience_for(item.get("kind")) == CLASSROOM


def score_is_classroom_safe(percent: object) -> bool:
    """True when a numeric percentage clears `SCORE_FLOOR_PERCENT`.

    Rejects booleans explicitly: `True` is an int in Python and would otherwise
    read as 1%, which is a confusing way to fail rather than an obvious one.
    """
    if isinstance(percent, bool) or not isinstance(percent, (int, float)):
        return False
    return percent >= SCORE_FLOOR_PERCENT


def tag(item: dict) -> dict:
    """Return `item` with its `audience` set from the vocabulary.

    The audience is stamped from the kind rather than copied from whatever the
    source claimed, so a source cannot promote its own fact to the wall.
    """
    return {**item, "audience": audience_for(item.get("kind"))}


def classroom_only(items) -> list[dict]:
    """Every classroom-facing item, in the order given."""
    if not isinstance(items, (list, tuple)):
        return []
    return [item for item in items if classroom_safe(item)]
