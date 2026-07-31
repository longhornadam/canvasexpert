"""Ingest local writing evidence: scrub, segment, and store.

    py -m api.dailywriting.cli.ingest --input day.json
"""
from __future__ import annotations

import argparse
from pathlib import Path

from api.dailywriting.cli import _common
from api.dailywriting.core import ingest as ingest_module
from api.dailywriting.store import codec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dailywriting-ingest", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, required=True, help='JSON with {"reps": [...], "submissions": [...]}; submissions use pseudonyms.')
    parser.add_argument("--dry-run", action="store_true")
    _common.add_store_args(parser)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    document = _common.read_json(args.input)
    repository = None if args.dry_run else _common.build_repository(args)
    contexts = {record["rep_id"]: codec.rep_from_dict(record) for record in document.get("reps", [])}
    if repository:
        for context in contexts.values():
            repository.put_rep(context)
    processed = flagged = 0
    for raw in document.get("submissions", []):
        rep_id = raw["rep_id"]
        context = contexts.get(rep_id) or (repository.read_rep(rep_id) if repository else None)
        if context is None:
            raise _common.CommandError(f"submission {raw.get('submission_id')} names unknown rep {rep_id!r}")
        pseudonym = raw.get("pseudonym") or raw.get("pseudonym_id")
        if not pseudonym:
            raise _common.CommandError(f"submission {raw.get('submission_id')} has no pseudonym; this path never accepts a real identifier")
        submission = ingest_module.ingest(submission_id=raw["submission_id"], rep_id=rep_id, pseudonym_id=pseudonym, submitted_at=_common.parse_datetime(raw["submitted_at"]), text=raw.get("text", ""), context=context, vault=repository.vault if repository else None)
        if repository:
            repository.append_submission(submission)
        processed += 1
        codes = [flag.code for flag in submission.flags]
        flagged += bool(codes)
        print(f"{pseudonym:24} {rep_id:18} {submission.student_word_count} student word(s)" + (f" flags={','.join(codes)}" if codes else ""))
    print(f"\n{processed} submission(s) processed, {flagged} carrying a structural flag.")
    if args.dry_run:
        print("Dry run: nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_common.run(main))
