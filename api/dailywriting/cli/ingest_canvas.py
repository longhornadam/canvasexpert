"""Ingest one Canvas assignment's submissions into the writing record.

    py -m api.dailywriting.cli.ingest_canvas --course-id 111 --assignment-id 700010

Typed responses come from the local course catalog and CanvasMirror with no
network call at all. An uploaded Word document has no text in the mirror to
read, so each one costs one focused Canvas fetch and one bounded download --
see `api.dailywriting.canvas_attachments`. Nothing is ever written to Canvas.

Calls the same driver the web UI's ingest route calls
(`api.dailywriting.canvas_ingest.ingest_canvas_assignment`), so this command
exists to make that path runnable and testable without the web UI, not as a
second implementation of it.
"""
from __future__ import annotations

import argparse

from api.dailywriting.canvas_ingest import CanvasIngestError, ingest_canvas_assignment
from api.dailywriting.cli import _common


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dailywriting-ingest-canvas", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--course-id", required=True,
                        help="Canvas course id, as it appears in the local "
                             "Course Catalog and CanvasMirror.")
    parser.add_argument("--assignment-id", required=True,
                        help="Canvas assignment id.")
    _common.add_store_args(parser)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    repository = _common.build_repository(args)
    try:
        for line in ingest_canvas_assignment(
                args.course_id, args.assignment_id, repository=repository):
            print(line)
    except CanvasIngestError as exc:
        raise _common.CommandError(str(exc)) from exc
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_common.run(main))
