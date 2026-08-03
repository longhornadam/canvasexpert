"""Rewrite one student's retired pseudonym to their new one across every
stored span, after a teacher renames them in the identity vault.

    py -m api.dailywriting.cli.rewrite_pseudonym --old "Sparky McGee" --new "Juniper Weld"
    py -m api.dailywriting.cli.rewrite_pseudonym --old "..." --new "..." --dry-run

`api/dailywriting/core/scrub.py` stores the vault's pseudonym directly in a
stored span, deliberately: this product measured and rejected redacting a
name out of student writing (see that module's docstring), because
over-redaction destroyed the record it exists to keep. So a rename does not
remove anything -- it leaves the OLD pseudonym sitting in every span that
already carries it, including a span in ANOTHER student's writing that
happens to mention the renamed student by name. That old pseudonym might be
the one thing the rename exists to retire (the compromised-pseudonym case),
so it cannot simply be left in place. This module is the fix: it walks
every stored span and rewrites the old pseudonym to the new one, wherever
it landed.

Never runs on import, on app start, or on a read -- only an explicit call to
`rewrite_pseudonym`, or this file's own command line entry point, touches
the store. It is not wired into the rename routes
(`api/webui/routes/names.py`, `api/webui/routes/roster_updates.py`); the
caller is expected to invoke `rewrite_pseudonym` itself, right after the
vault records the rename, passing the exact old and new pseudonym strings.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from api.dailywriting.cli import _common
from api.dailywriting.core import segmentation
from api.dailywriting.store import codec
from api.dailywriting.store.repo import Repository, SUBMISSIONS
from api.storage_support import atomic_write_json


@dataclass(frozen=True)
class RewriteReport:
    """Counts only -- no student text or identifier passes through this."""
    files_scanned: int = 0
    files_changed: int = 0
    submissions_scanned: int = 0
    submissions_changed: int = 0


def _token_pairs(old_pseudonym: str, new_pseudonym: str) -> list[tuple[str, str]]:
    """(old, new) replacement pairs, longest-old-first.

    A stored span may hold the full pseudonym ("Sparky McGee") or only the
    first or last name alone, exactly as `feedback_scrub.build_replacement_map`
    can land any of the three at ingest. When both names have the same
    two-token shape, this pairs first-with-first and last-with-last so a
    partial mention is rewritten too, not just a full one. Longest pattern
    first so the full name is consumed before its own pieces could match
    again as separate, shorter patterns."""
    old_tokens = old_pseudonym.split()
    new_tokens = new_pseudonym.split()
    pairs = {(old_pseudonym, new_pseudonym)}
    if len(old_tokens) == 2 and len(new_tokens) == 2:
        pairs.add((old_tokens[0], new_tokens[0]))
        pairs.add((old_tokens[1], new_tokens[1]))
    return sorted(pairs, key=lambda pair: len(pair[0]), reverse=True)


def _rewrite_text(text: str, pairs: list[tuple[str, str]]) -> str:
    result = text
    for old, new in pairs:
        result = re.sub(rf"\b{re.escape(old)}\b", new, result, flags=re.IGNORECASE)
    return result


def _rewrite_finding(finding: dict, pairs: list[tuple[str, str]]) -> dict:
    """Swap a finding's recorded `replacement` value old-for-new too.

    `replacement` is the exact pseudonym text a finding says landed at that
    span; leaving it holding the old pseudonym after a rename would just
    relocate the stale token into a different field of the same document.
    Position (`span_start`/`span_end`) is left as recorded: findings are
    audit metadata with no consumer that reads them back (they are never
    part of any outbound or teacher-facing payload -- see
    `api.dailywriting.projection`), so re-deriving exact offsets here is not
    worth the added complexity that re-deriving segments and flags already
    costs, below."""
    replacement = finding.get("replacement", "")
    for old, new in pairs:
        if replacement.lower() == old.lower():
            return {**finding, "replacement": new}
    return finding


def _rewrite_one(document: dict, *, pairs: list[tuple[str, str]],
                 repository: Repository) -> tuple[dict, bool]:
    """Rewrite one stored submission dict. Returns (rewritten_dict, changed)."""
    old_raw = document.get("raw_text", "")
    new_raw = _rewrite_text(old_raw, pairs)
    if new_raw == old_raw:
        return document, False

    rewritten = dict(document)
    rewritten["raw_text"] = new_raw
    rewritten["scrub_findings"] = [
        _rewrite_finding(finding, pairs)
        for finding in document.get("scrub_findings", [])
    ]

    context = repository.read_rep(document.get("rep_id"))
    if context is not None:
        # Re-segmenting the corrected text is exactly what ingest would
        # produce today, so segments and flags come out with valid offsets
        # against the NEW raw_text rather than needing every stored offset
        # hand-shifted by however much the new pseudonym's length differs
        # from the old one.
        result = segmentation.segment_submission(new_raw, context)
        rewritten["segments"] = [codec.segment_to_dict(s) for s in result.segments]
        rewritten["flags"] = [codec.flag_to_dict(f) for f in result.flags]
    else:
        # No assignment record to re-segment against. Should not happen in a
        # healthy store (ingest always writes the rep first), but a best
        # effort beats losing the record's segmentation outright: rewrite
        # each stored span's own text in place and leave its offsets as
        # recorded.
        rewritten["segments"] = [
            {**segment, "text": _rewrite_text(segment.get("text", ""), pairs)}
            for segment in document.get("segments", [])
        ]
        rewritten["flags"] = [
            {**flag,
             "detail": _rewrite_text(flag.get("detail", ""), pairs),
             "span": ({**flag["span"], "text": _rewrite_text(flag["span"].get("text", ""), pairs)}
                     if flag.get("span") else None)}
            for flag in document.get("flags", [])
        ]
    return rewritten, True


def rewrite_pseudonym(repository: Repository, *, old_pseudonym: str,
                      new_pseudonym: str, dry_run: bool = False) -> RewriteReport:
    """Rewrite `old_pseudonym` to `new_pseudonym` across every stored span in
    `repository`, including a mention of the renamed student inside another
    student's own submission.

    One file at a time, and one file's rewrite is atomic
    (`atomic_write_json`): a run interrupted mid-way leaves every file it
    has not yet reached completely untouched, and the file it was writing
    either lands whole or not at all -- never half-rewritten. Re-running
    with the same arguments against an already-rewritten store finds
    nothing left carrying the old pseudonym anywhere and rewrites nothing,
    so a repeated run is idempotent.

    `dry_run=True` reports what would change without writing anything.

    Call this once, right after the identity vault records the rename (see
    `api/webui/routes/names.py`); it is not invoked automatically by
    anything in this package.
    """
    pairs = _token_pairs(old_pseudonym, new_pseudonym)

    files_scanned = files_changed = 0
    submissions_scanned = submissions_changed = 0

    submissions_dir = repository.root / SUBMISSIONS
    if submissions_dir.exists():
        for path in sorted(submissions_dir.glob("*.json")):
            files_scanned += 1
            document = json.loads(path.read_text(encoding="utf-8"))
            entries = document.get("submissions", [])
            new_entries = []
            changed_any = False
            for entry in entries:
                submissions_scanned += 1
                rewritten, changed = _rewrite_one(
                    entry, pairs=pairs, repository=repository)
                new_entries.append(rewritten)
                if changed:
                    changed_any = True
                    submissions_changed += 1
            if changed_any:
                if not dry_run:
                    atomic_write_json(path, {
                        "schema": document.get("schema", codec.DOCUMENT_VERSION),
                        "submissions": new_entries,
                    })
                files_changed += 1

    return RewriteReport(
        files_scanned=files_scanned, files_changed=files_changed,
        submissions_scanned=submissions_scanned,
        submissions_changed=submissions_changed,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dailywriting-rewrite-pseudonym", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--old", required=True, dest="old_pseudonym",
                        help="the retired pseudonym, exactly as it was stored.")
    parser.add_argument("--new", required=True, dest="new_pseudonym",
                        help="the student's new current pseudonym.")
    _common.add_store_args(parser)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report what would change; write nothing.")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    repository = _common.build_repository(args)
    report = rewrite_pseudonym(
        repository, old_pseudonym=args.old_pseudonym,
        new_pseudonym=args.new_pseudonym, dry_run=args.dry_run)
    print(f"{report.files_scanned} file(s) scanned, {report.files_changed} rewritten.")
    print(f"{report.submissions_scanned} submission(s) scanned, "
         f"{report.submissions_changed} rewritten.")
    if args.dry_run:
        print("Dry run: nothing was written.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_common.run(main))
