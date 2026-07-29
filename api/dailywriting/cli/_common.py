"""Shared plumbing for the daily writing command line.

Every command here is local and read-or-write-to-disk only. None of them touch
Canvas or create gradebook state.

Output is pseudonymised because the store is: a command prints "Sparky McGee"
because that is the only name it has. Nothing here resolves back to a real
student, which is what makes the output safe to paste into a note to yourself.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from api.dailywriting.config import naming
from api.dailywriting.store.identity import MappingResolver
from api.dailywriting.store.repo import Repository, workspace_store_root


class CommandError(RuntimeError):
    """Something the user can fix. Printed without a traceback."""


def add_store_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--store-root", type=Path, default=None,
        help="where records live. Defaults to the workspace's private "
             f"_System/{naming.SYSTEM_NAME} folder.")
    parser.add_argument(
        "--identity-map", type=Path, default=None,
        help="JSON object mapping canvas id to pseudonym, for running without "
             "the identity vault (fixtures, dry runs).")


def build_repository(args) -> Repository:
    """A repository from the arguments, or the workspace default.

    An explicit `--identity-map` keeps the command runnable with no vault and
    no workspace, which is how the fixtures are exercised. Without it the
    vault is the only source of the pseudonym mapping, as INV-7 requires.
    """
    if args.identity_map:
        mapping = json.loads(Path(args.identity_map).read_text(encoding="utf-8"))
        resolver = MappingResolver({str(k): v for k, v in mapping.items()})
        root = args.store_root or workspace_store_root()
        return Repository(root, resolver=resolver, vault=None)
    repository = Repository.default()
    if args.store_root:
        return Repository(args.store_root, resolver=repository.resolver,
                          vault=repository.vault)
    return repository


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CommandError(f"{value!r} is not a date in YYYY-MM-DD form") from exc


def parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise CommandError(
            f"{value!r} is not an ISO timestamp; include the offset, as in "
            "2026-11-02T09:15:00-06:00") from exc


def read_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CommandError(f"no file at {path}") from exc
    except json.JSONDecodeError as exc:
        raise CommandError(f"{path} is not valid JSON: {exc}") from exc


def run(main_fn, argv=None) -> int:
    """Turn a CommandError into a message rather than a traceback."""
    try:
        return main_fn(argv)
    except CommandError as exc:
        print(f"error: {exc}")
        return 2
