"""Report large Python and JavaScript source files.

This is an advisory refactor aid, not a blocking quality gate. It prints compact
line-count buckets so agents can pick small, reviewable cleanup slices.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "out",
    "temp",
    "Finished_Exports",
    "PowerGrader",
    "FeedbackExpert",
}


def iter_source_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".py", ".js"}:
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in DEFAULT_SKIP_DIRS for part in rel_parts[:-1]):
            continue
        yield path


def line_count(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return sum(1 for _ in fh)
    except UnicodeDecodeError:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)


def build_report(root: Path, warn: int, large: int):
    rows = []
    for path in iter_source_files(root):
        lines = line_count(path)
        if lines >= warn:
            rows.append({
                "lines": lines,
                "level": "large" if lines >= large else "warn",
                "path": path.relative_to(root).as_posix(),
            })
    return sorted(rows, key=lambda row: (-row["lines"], row["path"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root to scan.")
    parser.add_argument("--warn", type=int, default=300, help="Report files at or above this line count.")
    parser.add_argument("--large", type=int, default=500, help="Mark files at or above this line count as large.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a text table.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    rows = build_report(root, args.warn, args.large)
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    print(f"Source files >= {args.warn} lines under {root}")
    if not rows:
        print("(none)")
        return 0

    width = max(len(row["path"]) for row in rows)
    for row in rows:
        print(f"{row['lines']:>5}  {row['level']:<5}  {row['path']:<{width}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
