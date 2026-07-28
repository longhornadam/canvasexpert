"""Drive one Canvas assignment's typed submissions into the writing record.

Pointing this at an assignment IS the opt-in (brief Section 8, option 1): no
persistent flag, no new store, no staleness to track for a flag nobody has
asked for yet. Re-running is safe and cheap -- `canvas_source.rep_id_for` /
`submission_id_for` are deterministic, so a second run overwrites the same
rep and the same submissions rather than duplicating them.

Reads only two local, disk-only sources, never Canvas:

  - the course catalog (`api.course_catalog`), for the assignment's prompt
    and dates -- read directly, not through `get_course_assignments`, so the
    prompt is never that MCP tool's preview truncation;
  - the CanvasMirror (`api.mirror.read_service`), for the roster (so the
    scrub map covers every enrolled student, exactly the discipline
    `get_submissions` documents -- brief, "a correctness trap") and each
    student's current typed submission body.

A stale or missing catalog/mirror is refused outright (`CanvasIngestError`),
the same posture the MCP tools take toward a stale mirror, for the same
reason: there is no live fallback to paper over it with, because this module
imports no Canvas transport at all (AC8). A missing identity-vault entry for
one submission's author is different -- not every enrolled student submitted,
but a submission from someone the roster sync did not cover is a data gap
worth surfacing, not a reason to withhold everyone else's rep (AC5): that one
submission is skipped and counted, the run continues.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from api import course_catalog, roster_service
from api.dailywriting import canvas_source
from api.dailywriting.core import ingest as ingest_module
from api.dailywriting.store.identity import IdentityError
from api.dailywriting.store.repo import Repository
from api.mirror import queries as mirror_queries
from api.mirror import read_service
from api.nq_report import html_to_text


class CanvasIngestError(RuntimeError):
    """The whole ingest is refused: nothing was written.

    Raised only before any store write happens (no catalog, no such
    assignment, or a stale/missing mirror) -- never partway through the
    per-submission loop, so a caller never has to wonder whether some
    students' reps landed and others did not.
    """


def _no_catalog_error() -> str:
    return ("No local course catalog for this course. Refresh the Course "
            "Catalog from the CanvasExpert web UI, then try again.")


def _no_assignment_error(course_id: str, assignment_id: str) -> str:
    return (f"No assignment {assignment_id} in course {course_id}'s local "
            "catalog. Confirm the assignment id, or refresh the Course "
            "Catalog if it was created recently, then try again.")


def _stale_mirror_error(course_id: str) -> str:
    return (
        f"The local CanvasMirror for course {course_id} (roster or "
        "submissions) is stale or missing. The writing record is ingested "
        "only from a fresh mirror, never live Canvas -- sync this course "
        "from the CanvasExpert web UI (Home > Sync now), then try again."
    )


def _typed_text(row: dict) -> str:
    return html_to_text(row.get("body") or "").strip()


def ingest_canvas_assignment(
    course_id: str, assignment_id: str, *, repository: Repository | None = None,
) -> Iterator[str]:
    """Ingest one assignment's typed submissions. Yields progress lines.

    Raises `CanvasIngestError` (before any write) when the catalog or mirror
    cannot serve. Per-submission gaps (no identity-vault entry, no body, no
    submitted_at) are skipped and counted, not raised -- see module docstring.
    """
    course_id, assignment_id = str(course_id), str(assignment_id)

    catalog_read = course_catalog.read_catalog(course_id)
    catalog = catalog_read.get("catalog")
    if not isinstance(catalog, dict):
        raise CanvasIngestError(_no_catalog_error())
    assignment = ((catalog.get("assignments") or {}).get("records") or {}).get(
        assignment_id)
    if assignment is None:
        raise CanvasIngestError(_no_assignment_error(course_id, assignment_id))

    max_age_hours = mirror_queries._serve_max_age_hours()
    roster_scope = read_service.private_roster(course_id, max_age_hours=max_age_hours)
    submissions_scope = read_service.private_submissions(
        course_id, max_age_hours=max_age_hours)
    if roster_scope["state"] != "current" or submissions_scope["state"] != "current":
        raise CanvasIngestError(_stale_mirror_error(course_id))

    repository = repository or Repository.default()
    vault = repository.vault
    if vault is not None:
        # Sync the full roster first so the scrub map covers every enrolled
        # student, not just the ones who submitted this assignment -- the
        # same discipline `get_submissions` documents, for the same reason:
        # a classmate named in someone's essay who did not submit this
        # assignment must still scrub, or their name leaks.
        with vault.transaction():
            roster_service.upsert_roster(vault, roster_scope["records"])

    rep_id = canvas_source.rep_id_for(course_id, assignment_id)
    context = canvas_source.assignment_context(assignment, rep_id=rep_id)
    repository.put_rep(context)
    prompt_note = ("empty" if not context.prompt_text
                   else f"{len(context.prompt_text)} chars")
    yield (f"rep {rep_id} stored: date={context.date.isoformat()}, "
           f"prompt={prompt_note}, unscored (tier={context.tier})")

    rows = [row for row in submissions_scope["records"]
            if str(row.get("assignment_id")) == assignment_id]

    processed = no_text = no_timestamp = no_identity = 0
    for row in rows:
        text = _typed_text(row)
        if not text:
            no_text += 1
            continue
        submitted_at_raw = row.get("submitted_at")
        try:
            submitted_at = datetime.fromisoformat(
                str(submitted_at_raw).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            no_timestamp += 1
            continue

        canvas_user_id = row.get("user_id")
        try:
            pseudonym_id = repository.resolver.to_pseudonym(canvas_user_id)
        except IdentityError:
            no_identity += 1
            continue

        submission_id = canvas_source.submission_id_for(
            course_id, assignment_id, canvas_user_id)
        result = ingest_module.ingest_unscored(
            submission_id=submission_id,
            rep_id=rep_id,
            pseudonym_id=pseudonym_id,
            submitted_at=submitted_at,
            text=text,
            context=context,
            vault=vault,
        )
        repository.append_submission(result.submission)
        repository.append_observations(result.observations)
        processed += 1
        yield (f"{pseudonym_id}: ingested, "
               f"{result.submission.student_word_count} student word(s)")

    summary = f"{processed} submission(s) ingested for {rep_id}."
    skips = []
    if no_identity:
        skips.append(f"{no_identity} skipped (no identity-vault entry for "
                     "the author -- sync the roster and re-run to pick "
                     "them up)")
    if no_timestamp:
        skips.append(f"{no_timestamp} skipped (no submitted_at timestamp)")
    if no_text:
        skips.append(f"{no_text} not typed text (nothing to ingest)")
    if skips:
        summary += " " + "; ".join(skips) + "."
    yield summary
