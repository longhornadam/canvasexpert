"""Ingest a day's reps: scrub, segment, score, observe, evaluate directives.

    py -m api.dailywriting.cli.ingest --input day.json

The input file carries reps and submissions, and identifies students by
pseudonym rather than by Canvas id, because that is the form the submissions
arrive in from the pseudonymising read path. Nothing here writes to Canvas.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from api.dailywriting.cli import _common
from api.dailywriting.core import ingest as ingest_module
from api.dailywriting.store import codec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dailywriting-ingest", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, required=True,
                        help='JSON with {"reps": [...], "submissions": [...]}. '
                             "Submissions identify students by pseudonym.")
    parser.add_argument("--dry-run", action="store_true",
                        help="process and report without writing any record.")
    _common.add_store_args(parser)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    document = _common.read_json(args.input)

    submissions = document.get("submissions") or []
    if not submissions:
        raise _common.CommandError(f"{args.input} lists no submissions")

    reps = {raw["rep_id"]: codec.rep_from_dict(raw)
            for raw in document.get("reps", [])}
    repository = None if args.dry_run else _common.build_repository(args)
    if repository is not None:
        for context in reps.values():
            repository.put_rep(context)

    criteria_cache: dict = {}
    processed = flagged = 0
    for raw in submissions:
        rep_id = raw.get("rep_id")
        context = reps.get(rep_id)
        if context is None and repository is not None:
            context = repository.read_rep(rep_id)
        if context is None:
            raise _common.CommandError(
                f"submission {raw.get('submission_id')} names rep {rep_id!r}, "
                "which is neither in the input file nor already stored")

        pseudonym = raw.get("pseudonym") or raw.get("pseudonym_id")
        if not pseudonym:
            raise _common.CommandError(
                f"submission {raw.get('submission_id')} has no pseudonym; this "
                "path never takes a real name or Canvas id")

        result = ingest_module.ingest(
            submission_id=raw["submission_id"],
            rep_id=rep_id,
            pseudonym_id=pseudonym,
            submitted_at=_common.parse_datetime(raw["submitted_at"]),
            text=raw.get("text", ""),
            context=context,
            criteria_set=_common.criteria_for(context.tier, criteria_cache),
            open_directives=(repository.directives_for(pseudonym)
                             if repository is not None else ()),
            vault=repository.vault if repository is not None else None,
        )

        if repository is not None:
            repository.append_submission(result.submission)
            repository.append_score(result.score, pseudonym)
            repository.append_observations(result.observations)
            for directive in result.directives:
                repository.put_directive(directive)

        processed += 1
        codes = [flag.code for flag in result.submission.flags]
        flagged += 1 if codes else 0
        acknowledgment = result.acknowledgment
        print(f"{pseudonym:24} {rep_id:18} "
              f"{result.score.total}/{result.score.possible} "
              f"{result.score.status}"
              + (f"  flags={','.join(codes)}" if codes else "")
              + (f"  ack={acknowledgment.kind}" if acknowledgment else ""))

    print(f"\n{processed} submission(s) processed, {flagged} carrying a flag "
          "for human eyes.")
    if args.dry_run:
        print("Dry run: nothing was written.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_common.run(main))
