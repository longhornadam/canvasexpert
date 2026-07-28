"""Build one section's weekly digest.

    py -m api.dailywriting.cli.digest --section ELA7-PREAP-2A \\
        --week-start 2026-11-02 --week-end 2026-11-06

This is the aggregate read: top failure modes with real spans under them,
per-criterion class rates against last week, who is ready to move up, who let a
directive lapse, who turned in nothing, and what the segmenter was unsure about.

Pass `--students-file` with the section roster to get a trustworthy
"turned in nothing" list. Without it the command says so rather than quietly
reporting a short list as if it were complete.
"""
from __future__ import annotations

import argparse
from datetime import timedelta

from api.dailywriting.cli import _common
from api.dailywriting.core import digest as digest_module


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dailywriting-digest", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--section", required=True)
    parser.add_argument("--week-start", required=True)
    parser.add_argument("--week-end", required=True)
    parser.add_argument("--students", nargs="*", default=None)
    parser.add_argument("--students-file", default=None,
                        help="the section roster as pseudonyms. Needed for a "
                             "complete missing-work list.")
    parser.add_argument("--tier", type=int, default=None,
                        help="criteria tier for the labels. Defaults to the "
                             "most common tier among this section's students.")
    _common.add_store_args(parser)
    return parser


def _dominant_tier(repository, students: list[str], submissions) -> int:
    """Which tier's labels to print.

    Taken from the reps in this window rather than from students' stored tiers:
    the digest labels the work it is showing, and a week of tier-4 reps read
    against tier-1 wording would quietly drop the criteria the class was
    actually measured on. Falls back to stored tiers when the window is empty.
    """
    counts: dict[int, int] = {}
    for submission in submissions:
        rep = repository.read_rep(submission.rep_id)
        if rep is not None:
            counts[rep.tier] = counts.get(rep.tier, 0) + 1
    if not counts:
        for pseudonym in students:
            tier = repository.current_tier(pseudonym)
            counts[tier] = counts.get(tier, 0) + 1
    if not counts:
        return 1
    return max(sorted(counts), key=lambda tier: counts[tier])


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    week_start = _common.parse_date(args.week_start)
    week_end = _common.parse_date(args.week_end)
    if week_start > week_end:
        raise _common.CommandError("--week-start is after --week-end")

    repository = _common.build_repository(args)
    students, warnings = _common.students_from(args, repository)
    for warning in warnings:
        print(f"note: {warning}")

    submissions = repository.section_submissions(students, week_start, week_end)
    tier = args.tier or _dominant_tier(repository, students, submissions)
    criteria = _common.criteria_for(tier)

    scores = repository.scores_for([s.submission_id for s in submissions])
    observations = repository.section_observations(students, week_start, week_end)
    directives = [d for pseudonym in students
                  for d in repository.directives_for(pseudonym)]
    profiles = [p for p in (repository.read_profile(pseudonym)
                            for pseudonym in students) if p is not None]

    prior_start = week_start - timedelta(days=7)
    prior_end = week_start - timedelta(days=1)
    prior_submissions = repository.section_submissions(students, prior_start,
                                                       prior_end)
    prior_scores = list(repository.scores_for(
        [s.submission_id for s in prior_submissions]).values())

    report = digest_module.build_digest(
        args.section, week_start, week_end,
        enrolled_pseudonyms=students,
        submissions=submissions,
        scores=scores,
        observations=observations,
        directives=directives,
        profiles=profiles,
        criteria_set=criteria,
        prior_week_scores=prior_scores,
    )

    print(f"\n{args.section}  {week_start.isoformat()} to {week_end.isoformat()}")
    print(f"{report.submissions_counted} submission(s) from "
          f"{report.students_counted} student(s), tier {tier} labels\n")

    print("Top failure modes")
    if not report.top_patterns:
        print("  nothing recorded this week")
    for pattern in report.top_patterns:
        print(f"  {pattern.pattern_tag:34} {pattern.count:3} "
              f"({pattern.share_of_submissions:.0%} of submissions, "
              f"{pattern.students_affected} students)")
        for span in pattern.example_spans:
            print(f"      \"{span[:96]}\"")

    print("\nPer-criterion class rate")
    for trend in report.criterion_trends:
        arrow = ""
        if trend.delta is not None:
            arrow = f"  {trend.delta:+.0%} vs last week"
        print(f"  {trend.met_rate:5.0%}  n={trend.scored:<3} "
              f"{trend.student_facing_text}{arrow}")

    if report.ready_for_tier_advance:
        print("\nReady for the next tier (recommendation only): "
              + ", ".join(report.ready_for_tier_advance))
    if report.lapsed_directives:
        print("\nLapsed directives")
        for pseudonym, text in report.lapsed_directives:
            print(f"  {pseudonym:24} {text}")
    if report.no_submissions_this_week:
        print("\nNothing turned in this week: "
              + ", ".join(report.no_submissions_this_week))
    if report.needs_human_eyes:
        print("\nNeeds human eyes")
        for note in report.needs_human_eyes:
            print(f"  {note.submission_id:18} {note.code}: {note.detail}")
    for note in report.coverage_notes:
        print(f"\nnote: {note}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_common.run(main))
