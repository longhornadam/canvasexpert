"""Standalone dev CLI for the Option-C paper render spike."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from engine.importers import import_quiz_from_llm
from engine.packaging.folder_creator import sanitize_filename
from engine.rendering.physical.emit_docx import html_to_docx
from engine.rendering.physical.emit_pdf import html_to_pdf
from engine.rendering.physical.html_renderer import default_css_path, render_html
from engine.rendering.physical.quiz_adapter import to_printdoc
from engine.rendering.physical.reference_doc import build_reference_docx


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a QuizForge quiz through the paper spike.")
    parser.add_argument("--input", required=True, help="Path to a QuizForge .json/.txt/.md file")
    parser.add_argument("--output", required=True, help="Directory for rendered spike outputs")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    imported = import_quiz_from_llm(input_path.read_text(encoding="utf-8"))
    printdoc = to_printdoc(imported.quiz)
    base = sanitize_filename(printdoc.title) or "Untitled_Quiz"

    quiz_html = render_html(printdoc, variant="quiz")
    key_html = render_html(printdoc, variant="key")

    quiz_html_path = output_dir / f"{base}_NEW.html"
    quiz_docx_path = output_dir / f"{base}_NEW.docx"
    quiz_pdf_path = output_dir / f"{base}.pdf"
    key_docx_path = output_dir / f"{base}_KEY_NEW.docx"
    key_pdf_path = output_dir / f"{base}_KEY.pdf"

    quiz_html_path.write_text(quiz_html, encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="ce-printdoc-") as tmpdir:
        reference_docx = build_reference_docx(str(Path(tmpdir) / "reference.docx"))
        try:
            html_to_docx(quiz_html, reference_docx, str(quiz_docx_path))
            html_to_docx(key_html, reference_docx, str(key_docx_path))
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    css_path = default_css_path()
    try:
        html_to_pdf(quiz_html, css_path, str(quiz_pdf_path))
        html_to_pdf(key_html, css_path, str(key_pdf_path))
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    for path in (quiz_html_path, quiz_docx_path, quiz_pdf_path, key_docx_path, key_pdf_path):
        print(path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
