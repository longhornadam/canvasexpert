"""Physical NoteForge output handler."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable

from engine.packaging.folder_creator import sanitize_filename
from engine.rendering.physical.redact import filled, redact
from engine.rendering.physical.tiers import TIERS


def generate_note_outputs(note: dict, output_folder: str) -> dict:
    """Generate tiered NoteForge DOCX/PDF outputs via the shared render substrate.

    The input is already-trusted NoteForge JSON. Validation belongs upstream.
    Converter failures are non-fatal and are reported in ``log_path``.
    """

    from engine.rendering.physical.emit_docx import html_to_docx
    from engine.rendering.physical.emit_pdf import html_to_pdf
    from engine.rendering.physical.html_renderer import default_css_path, render_html
    from engine.rendering.physical.note_adapter import to_printdoc
    from engine.rendering.physical.reference_doc import build_reference_docx

    out = Path(output_folder)
    out.mkdir(parents=True, exist_ok=True)

    printdoc = to_printdoc(note)
    base = sanitize_filename(printdoc.title) or "Untitled_Notes"
    log_path = out / "physical_validation.log"
    log_path.write_text("", encoding="utf-8")

    if note.get("mode") == "exemplar":
        docs = {"Exemplar": filled(printdoc)}
    else:
        docs = {tier: redact(printdoc, tier) for tier in TIERS}
    docs["KEY"] = filled(printdoc)

    artifacts: dict[str, dict[str, str]] = {
        label: {"docx_path": "", "pdf_path": ""} for label in docs
    }

    css_path = default_css_path()
    with tempfile.TemporaryDirectory(prefix="ce-noteforge-") as tmpdir:
        reference_docx = build_reference_docx(str(Path(tmpdir) / "reference.docx"))
        for label, doc in docs.items():
            html_tier = label if label not in {"KEY", "Exemplar"} else None
            html = render_html(doc, variant="note", tier=html_tier)
            docx_path = out / f"{base}_{label}.docx"
            pdf_path = out / f"{base}_{label}.pdf"

            _try_emit(
                lambda html=html, docx_path=docx_path: html_to_docx(
                    html, reference_docx, str(docx_path)
                ),
                f"note {label} docx",
                log_path,
            )
            _try_emit(
                lambda html=html, pdf_path=pdf_path: html_to_pdf(html, css_path, str(pdf_path)),
                f"note {label} pdf",
                log_path,
            )

            artifacts[label]["docx_path"] = str(docx_path) if docx_path.exists() else ""
            artifacts[label]["pdf_path"] = str(pdf_path) if pdf_path.exists() else ""

    return {"artifacts": artifacts, "log_path": str(log_path)}


def _try_emit(fn: Callable[[], str], label: str, log_path: Path) -> None:
    try:
        fn()
    except RuntimeError as exc:
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"PHYSICAL RENDER WARNING [{label}]: {exc}\n")
