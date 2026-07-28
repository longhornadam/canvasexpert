"""Re-score stored submissions against their published checklists.

    py -m api.dailywriting.cli.score --from 2026-11-01 --to 2026-11-30

Use after a scorer change, to replay the fix over past work instead of only
applying it going forward. Scores are append-only, so the earlier result stays
in the record for anyone auditing what the system used to think, and readers
take the latest.

Segments are not recomputed: this re-runs the checker over the attribution
already stored. Re-run ingest if segmentation itself changed.
"""
from __future__ import annotations

import argparse

from api.dailywriting import canvas_source
from api.dailywriting.cli import _common
from api.dailywriting.core import scoring


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dailywriting-score", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="start", required=True,
                        help="first day to re-score, YYYY-MM-DD")
    parser.add_argument("--to", dest="end", required=True,
                        help="last day to re-score, YYYY-MM-DD")
    parser.add_argument("--students", nargs="*", default=None,
                        help="pseudonyms to cover. Defaults to everyone with "
                             "records in the store.")
    parser.add_argument("--students-file", default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change without writing.")
    _common.add_store_args(parser)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    start = _common.parse_date(args.start)
    end = _common.parse_date(args.end)
    if start > end:
        raise _common.CommandError("--from is after --to")

    repository = _common.build_repository(args)
    students, warnings = _common.students_from(args, repository)
    for warning in warnings:
        print(f"note: {warning}")

    criteria_cache: dict = {}
    rescored = changed = skipped = 0

    for pseudonym in students:
        submissions = repository.submissions_in_window(pseudonym, start, end)
        previous = repository.scores_for([s.submission_id for s in submissions])
        for submission in submissions:
            context = repository.read_rep(submission.rep_id)
            if context is None:
                skipped += 1
                print(f"{pseudonym:24} {submission.rep_id:18} skipped: the rep "
                      "is not stored, so there is no prompt to score against")
                continue
            if canvas_source.is_unscorable(context):
                # A Canvas-sourced extended piece (ingested via
                # `ingest_unscored`) carries the UNSCORABLE_TIER /
                # UNSCORABLE_CRITERIA_SET_ID sentinel on purpose (brief
                # Section 3.4): a checklist chosen by `tier` would otherwise
                # silently grade a 400-1500 word essay against criteria
                # written for a one-sentence daily rep.
                skipped += 1
                print(f"{pseudonym:24} {submission.rep_id:18} skipped: this "
                      "rep was ingested unscored from Canvas (tier "
                      f"{context.tier} is not a real tier); a checklist "
                      "written for a daily rep cannot honestly grade it, so "
                      "it is never checklist-scored")
                continue
            criteria = _common.criteria_for(context.tier, criteria_cache)
            try:
                score = scoring.score_submission(
                    submission.segments_for_scoring(), criteria, context,
                    submission_id=submission.submission_id,
                    raw_text=submission.raw_text)
            except scoring.CriteriaNotPublishedError as exc:
                skipped += 1
                print(f"{pseudonym:24} {submission.rep_id:18} skipped: {exc}")
                continue

            rescored += 1
            before = previous.get(submission.submission_id)
            moved = before is None or before.total != score.total
            if moved:
                changed += 1
                was = f"{before.total}/{before.possible}" if before else "unscored"
                print(f"{pseudonym:24} {submission.rep_id:18} {was} -> "
                      f"{score.total}/{score.possible}")
            if not args.dry_run:
                repository.append_score(score, pseudonym)

    print(f"\n{rescored} submission(s) re-scored, {changed} changed, "
          f"{skipped} skipped.")
    if args.dry_run:
        print("Dry run: nothing was written.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_common.run(main))
