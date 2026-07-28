"""Canvas assignment -> `AssignmentContext`, and the deterministic ids that
make a re-ingest overwrite rather than duplicate.

Pure: every function here takes already-read catalog/mirror dicts and returns
typed values. No I/O, no Canvas import -- the driver that actually reads the
catalog and the mirror lives in `canvas_ingest.py`. This split exists because
the mapping decisions below are the part worth testing in isolation from disk
and the vault. Their reasoning is Section 5 of that batch's brief, retired when
the batch landed and readable at
`git show 401c7c0:docs/handoffs/CanvasExpert-WritingRecord-CanvasIngest-BRIEF.md`.

Decisions, one per required `AssignmentContext` field that has no direct
Canvas source:

  `date` -- `rep_date()` below: due_at, then unlock_at, then created_at.
  `tier` / `criteria_set_id` -- the UNSCORABLE_* sentinels below.
  `section_id` -- always `None`. A Canvas assignment carries no section
    (`assignment_group_id` is a grading category, not a section; sections
    exist only on the roster). Fanning out one rep per roster section was the
    alternative, but nothing yet consumes `Repository.reps(section_id=...)`
    for Canvas-sourced work, so `None` just opts these reps out of that
    filter -- reversible, and cheaper than a fan-out with no reader.
  `scaffold_blocks`, `source_texts`, `word_cap` -- empty/`None`. Parsing a
    stem, a source passage, or a word cap out of description prose is a
    guess; a wrong `{{BLANK}}` changes segmentation, and a guess is worse
    than admitting there is none.
"""
from __future__ import annotations

from datetime import date as date_cls, datetime

from api.dailywriting.core.models import AssignmentContext

# An unscored, Canvas-sourced rep must be UNMISTAKABLY unscorable, not merely
# unlikely to be scored by accident (brief Section 3.4): `cli/score.py`
# selects a checklist by `tier`, and a Canvas-sourced rep carrying a
# plausible-looking tier would be silently scored against criteria written
# for a one-sentence rep. `tier` stays an `int` and `criteria_set_id` stays a
# `str` -- `AssignmentContext`'s actual field types -- so this needs no store
# model or codec change: it is a value real criteria can never produce.
# `config.criteria_loader.TIER_FILES` only defines tiers 1-4, and no criteria
# file will ever be published with this id.
UNSCORABLE_TIER = 0
UNSCORABLE_CRITERIA_SET_ID = "unscored:canvas-typed"


class DateDerivationError(ValueError):
    """None of an assignment's due_at/unlock_at/created_at parse to a date."""


def _parse_date(value) -> date_cls | None:
    text = (value or "").strip() if isinstance(value, str) else ""
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def rep_date(assignment: dict) -> date_cls:
    """The rep's school-day date: due_at, then unlock_at, then created_at.

    In that order because that is how much each one means "when this was
    assigned as a school day": `due_at` is what a teacher means by "when this
    was due"; `unlock_at` is the next-best signal for an assignment with no
    due date but a release date; `created_at` is a last resort -- when the
    Canvas record was authored, not when the work happened, but still a real
    date on the assignment rather than an invented one.

    Refuses rather than falling back to "today" if none of the three parse:
    `date` is what `get_writing_history` sorts on, and a fabricated date is a
    silent corruption of that ordering, not a convenience.
    """
    for key in ("due_at", "unlock_at", "created_at"):
        parsed = _parse_date(assignment.get(key))
        if parsed is not None:
            return parsed
    raise DateDerivationError(
        f"assignment {assignment.get('id')!r} has no due_at, unlock_at, or "
        "created_at to derive a rep date from"
    )


def rep_id_for(course_id: str, assignment_id: str) -> str:
    """Deterministic so a re-run replaces the same rep (`put_rep`,
    `store/repo.py:225`) instead of creating a sibling. The `canvas:` prefix
    makes a Canvas-sourced rep recognisable at a glance in `reps.json`, on
    top of (not instead of) the tier/criteria_set_id sentinel that actually
    keeps it out of the scored path."""
    return f"canvas:{course_id}:{assignment_id}"


def submission_id_for(course_id: str, assignment_id: str, canvas_user_id) -> str:
    """Deterministic so a re-run overwrites the same submission (read-
    idempotent via `_latest_by`, `store/repo.py:126`) instead of duplicating.

    Carries no attempt number. `read_service.private_submissions` -- the read
    this driver uses -- surfaces only each student's CURRENT attempt per
    assignment (`api/mirror/store.py` `normalize_submission`'s `current`,
    never the `attempts` history), so there is nothing to disambiguate: a
    resubmission simply replaces this id's stored content on the next
    ingest, the same "current" semantics every other mirror-backed read
    already has for this data.
    """
    return f"canvas:{course_id}:{assignment_id}:{canvas_user_id}"


def assignment_context(assignment: dict, *, rep_id: str) -> AssignmentContext:
    """Build the `AssignmentContext` for one Canvas assignment record.

    `assignment` is one record from the course catalog's `assignments` scope
    (`api.course_catalog.normalize_assignment` shape: `id`, `description_text`,
    `due_at`, `unlock_at`, `created_at`, ...) -- read directly from the
    catalog document, never through `get_course_assignments`, so the prompt
    is never that MCP tool's preview truncation (brief Section 3.5).

    `prompt_text` empty is stored as empty: `description_text` is already
    whatever `api.course_catalog._description_text` produced (possibly ""),
    and nothing here substitutes a placeholder for it.
    """
    return AssignmentContext(
        rep_id=rep_id,
        date=rep_date(assignment),
        tier=UNSCORABLE_TIER,
        prompt_text=assignment.get("description_text") or "",
        criteria_set_id=UNSCORABLE_CRITERIA_SET_ID,
        scaffold_blocks=[],
        source_texts=[],
        word_cap=None,
        section_id=None,
    )


def is_unscorable(context: AssignmentContext) -> bool:
    """True for a rep built by `assignment_context()` above.

    The check `cli/score.py` uses to refuse a Canvas-sourced rep loudly
    rather than scoring it against a checklist chosen by `tier` (brief
    Section 3.4, AC6). Either sentinel alone would do; checking both is
    cheap and does not depend on which one a future caller happens to set.
    """
    return (context.tier == UNSCORABLE_TIER
            or context.criteria_set_id == UNSCORABLE_CRITERIA_SET_ID)
