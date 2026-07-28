"""Blind calibration: score a stratified sample yourself, then compare.

    py -m api.dailywriting.cli.calibrate sample --from 2026-10-01 --to 2026-10-31
    py -m api.dailywriting.cli.calibrate agreement --sample-id 2026-10 \\
        --answers my-scores.json

This is what keeps confidence in the instrument falsifiable. Once a month, the
sample command hands you twenty submissions stratified across the score range
with the machine's scores hidden. You score them blind, and the agreement
command reports per-criterion agreement, naming every disagreement so you can
look at the actual sentence rather than a percentage.

Low agreement on a criterion is information about the checker, not about the
students. Move the threshold in config/thresholds.py, or move the criterion to
a model read, and calibrate again.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from api.dailywriting.cli import _common
from api.dailywriting.config import thresholds
from api.dailywriting.core import digest as digest_module


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dailywriting-calibrate", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    sample = subparsers.add_parser(
        "sample", help="build a blind-scoring sample")
    sample.add_argument("--from", dest="start", required=True)
    sample.add_argument("--to", dest="end", required=True)
    sample.add_argument("--sample-id", default=None,
                        help="defaults to the window's start month")
    sample.add_argument("--size", type=int,
                        default=thresholds.CALIBRATION_SAMPLE_SIZE)
    sample.add_argument("--strata", type=int,
                        default=thresholds.CALIBRATION_STRATA)
    sample.add_argument("--out", type=Path, default=None,
                        help="also write a scoring sheet here")
    sample.add_argument("--students", nargs="*", default=None)
    sample.add_argument("--students-file", default=None)
    _common.add_store_args(sample)

    agreement = subparsers.add_parser(
        "agreement", help="compare your blind scores against the machine's")
    agreement.add_argument("--sample-id", required=True)
    agreement.add_argument("--answers", type=Path, required=True,
                           help='JSON: {"<submission_id>": {"<item_id>": true}}')
    _common.add_store_args(agreement)
    return parser


def _do_sample(args) -> int:
    start = _common.parse_date(args.start)
    end = _common.parse_date(args.end)
    if start > end:
        raise _common.CommandError("--from is after --to")

    repository = _common.build_repository(args)
    students, warnings = _common.students_from(args, repository)
    for warning in warnings:
        print(f"note: {warning}")

    submissions = repository.section_submissions(students, start, end)
    scores = repository.scores_for([s.submission_id for s in submissions])
    sample_id = args.sample_id or f"{start.year:04d}-{start.month:02d}"

    sample = digest_module.build_calibration_sample(
        submissions, scores, sample_id=sample_id, size=args.size,
        strata=args.strata)
    if not sample.items:
        raise _common.CommandError(
            "no scored work in that window, so there is nothing to calibrate on")

    repository.put_calibration(sample)

    by_stratum: dict[int, int] = {}
    for item in sample.items:
        by_stratum[item.stratum] = by_stratum.get(item.stratum, 0) + 1
    print(f"sample {sample.sample_id}: {len(sample.items)} submission(s) across "
          f"{len(by_stratum)} of {sample.strata} score bands "
          + str({k: by_stratum[k] for k in sorted(by_stratum)}))
    print("Machine scores are not in this sample. Score it blind, then run "
          "the agreement command.\n")

    if args.out:
        sheet = {
            "sample_id": sample.sample_id,
            "_instructions": (
                "For each submission, mark each criterion true or false as you "
                "would score it. Do not look at the stored scores first."),
            "scores": {item.submission_id: {} for item in sample.items},
            "submissions": [
                {"submission_id": item.submission_id,
                 "criteria_set_id": item.criteria_set_id,
                 "text": item.text}
                for item in sample.items
            ],
        }
        Path(args.out).write_text(json.dumps(sheet, indent=2), encoding="utf-8")
        print(f"scoring sheet written to {args.out}")
    else:
        for item in sample.items:
            print(f"  [{item.stratum}] {item.submission_id}: "
                  f"{item.text.strip()[:110]}")
    return 0


def _do_agreement(args) -> int:
    repository = _common.build_repository(args)
    sample = repository.read_calibration(args.sample_id)
    if sample is None:
        raise _common.CommandError(
            f"no stored calibration sample {args.sample_id!r}; run the sample "
            "command first")

    document = _common.read_json(args.answers)
    teacher = document.get("scores", document)
    if not isinstance(teacher, dict) or not teacher:
        raise _common.CommandError(
            f"{args.answers} has no scores; expected "
            '{"<submission_id>": {"<item_id>": true}}')
    teacher = {key: value for key, value in teacher.items() if value}

    machine = repository.scores_for(sample.submission_ids)
    report = digest_module.calibration_agreement(sample, machine, teacher)

    if not report.compared_submissions:
        raise _common.CommandError(
            "none of the scored submissions in your answers file are in this "
            "sample, so there is nothing to compare")

    print(f"\nsample {report.sample_id}: {report.compared_submissions} of "
          f"{len(sample.items)} submission(s) scored blind")
    print(f"overall agreement {report.overall_rate:.0%}\n")
    for criterion in report.per_criterion:
        print(f"  {criterion.rate:5.0%}  {criterion.agreed}/{criterion.compared}"
              f"  {criterion.item_id}")

    if report.disagreements:
        print("\nDisagreements (machine, then you)")
        for submission_id, item_id, machine_met, teacher_met in report.disagreements:
            print(f"  {submission_id:18} {item_id:32} "
                  f"{'met' if machine_met else 'not met':8} vs "
                  f"{'met' if teacher_met else 'not met'}")
        print("\nLook at the sentences behind these before changing a "
              "threshold. A criterion the checker cannot settle belongs on a "
              "model read, not on a tuned number.")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "sample":
        return _do_sample(args)
    return _do_agreement(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_common.run(main))
