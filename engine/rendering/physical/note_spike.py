"""Standalone dev CLI for NoteForge guided-cloze tiered output."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from engine.packaging.folder_creator import sanitize_filename
from engine.rendering.physical.emit_docx import html_to_docx
from engine.rendering.physical.emit_pdf import html_to_pdf
from engine.rendering.physical.html_renderer import default_css_path, render_html
from engine.rendering.physical.note_adapter import load_noteforge_json, to_printdoc
from engine.rendering.physical.redact import filled, redact
from engine.rendering.physical.reference_doc import build_reference_docx
from engine.rendering.physical.tiers import TIERS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render NoteForge guided-cloze notes as tiered PDF + DOCX files."
    )
    parser.add_argument("--input", required=True, help="Path to a tagged or raw NoteForge JSON file")
    parser.add_argument("--output", required=True, help="Directory for rendered note outputs")
    parser.add_argument(
        "--tiers",
        default=",".join(TIERS),
        help="Comma-separated tier labels to emit for blank-mode notes",
    )
    args = parser.parse_args(argv)

    note = load_noteforge_json(args.input)
    printdoc = to_printdoc(note)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        selected_tiers = _parse_tiers(args.tiers)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    base = sanitize_filename(printdoc.title) or "Untitled_Notes"

    if note.get("mode") == "exemplar":
        docs = {"Exemplar": filled(printdoc)}
    else:
        docs = {tier: redact(printdoc, tier) for tier in selected_tiers}
    docs["KEY"] = filled(printdoc)

    css_path = default_css_path()
    written: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="ce-noteforge-") as tmpdir:
        reference_docx = build_reference_docx(str(Path(tmpdir) / "reference.docx"))
        for label, doc in docs.items():
            html_tier = label if label not in {"KEY", "Exemplar"} else None
            html = render_html(doc, variant="note", tier=html_tier)
            docx_path = output_dir / f"{base}_{label}.docx"
            pdf_path = output_dir / f"{base}_{label}.pdf"

            try:
                html_to_docx(html, reference_docx, str(docx_path))
                html_to_pdf(html, css_path, str(pdf_path))
            except RuntimeError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 2
            written.extend([docx_path, pdf_path])

    for path in written:
        print(path)

    return 0


def _parse_tiers(raw: str) -> list[str]:
    tiers = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [tier for tier in tiers if tier not in TIERS]
    if unknown:
        raise ValueError(f"unknown tier(s): {', '.join(unknown)}")
    return tiers


if __name__ == "__main__":
    raise SystemExit(main())
