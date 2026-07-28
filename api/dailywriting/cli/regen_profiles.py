"""Regenerate rolling profiles from the record.

    py -m api.dailywriting.cli.regen_profiles --as-of 2026-11-14

Profiles are derived and replaceable, so this is always safe to re-run and
deleting them costs one regeneration and no information. Patterns re-earn their
place from in-window evidence every time (INV-4): a habit that stopped shows up
as gone, not as a smaller number.

`ready_for_tier_advance` is printed as a recommendation. Nothing here promotes
anyone; tier changes are `set_tier`, and that is the teacher's call.
"""
from __future__ import annotations

import argparse

from api.dailywriting.cli import _common
from api.dailywriting.config import thresholds
from api.dailywriting.core import profile as profile_module


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dailywriting-regen-profiles", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--as-of", dest="as_of", required=True,
                        help="the window's last day, YYYY-MM-DD")
    parser.add_argument("--window-weeks", type=int,
                        default=thresholds.PROFILE_WINDOW_WEEKS)
    parser.add_argument("--students", nargs="*", default=None,
                        help="pseudonyms to regenerate. Defaults to everyone "
                             "with records in the store.")
    parser.add_argument("--students-file", default=None)
    parser.add_argument("--dry-run", action="store_true")
    _common.add_store_args(parser)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    as_of = _common.parse_date(args.as_of)
    if args.window_weeks < 1:
        raise _common.CommandError("--window-weeks must be at least 1")

    repository = _common.build_repository(args)
    students, warnings = _common.students_from(args, repository)
    for warning in warnings:
        print(f"note: {warning}")

    criteria_cache: dict = {}
    ready: list[str] = []
    lapsed: list[str] = []

    for pseudonym in students:
        tier = repository.current_tier(pseudonym)
        criteria = _common.criteria_for(tier, criteria_cache)
        rolling = profile_module.regenerate_profile(
            pseudonym, as_of, args.window_weeks,
            source=repository, criteria_set=criteria)

        if not args.dry_run:
            repository.put_profile(rolling)

        patterns = ", ".join(f"{p.pattern_tag}x{p.count}"
                             for p in rolling.active_patterns) or "none"
        print(f"{pseudonym:24} tier {rolling.tier}  "
              f"patterns: {patterns}")
        print(f"{'':24} next: {rolling.next_focus}")
        if rolling.ready_for_tier_advance:
            ready.append(pseudonym)
        if any(d.status == "lapsed" for d in rolling.open_directives):
            lapsed.append(pseudonym)

    print(f"\n{len(students)} profile(s) regenerated over "
          f"{args.window_weeks} week(s) ending {as_of.isoformat()}.")
    if ready:
        print("Recommended for the next tier (your call, nothing moved): "
              + ", ".join(ready))
    if lapsed:
        print("Has a lapsed directive: " + ", ".join(lapsed))
    if args.dry_run:
        print("Dry run: nothing was written.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_common.run(main))
