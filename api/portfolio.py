"""Render a student's New Quizzes writing into a compiled portfolio DOCX.

Phase 1: builds a per-student document from parsed student_analysis data alone — an
MC performance summary plus the constructed (written) responses as prompt -> response
blocks. Phase 2 will merge live Assignment text entries + uploaded files/photos into
the same document (see the plan). Reuses python-docx (already a dependency; same
pattern as api/student_packet.py).

PII: portfolio documents are real student work — callers must write them only to the
synced student-reports root / gitignored output, never into the repo.
"""
import os
import re
from datetime import datetime

from docx import Document

try:                                   # script context (run from api/)
    from nq_report import constructed_responses, html_to_text
except ModuleNotFoundError:            # package context (tests: api.portfolio)
    from api.nq_report import constructed_responses, html_to_text


def _safe(name: str, max_len: int = 80) -> str:
    """Filesystem-safe stem (local copy so this module stays import-light)."""
    cleaned = re.sub(r'[^\w\- ]+', "", (name or "").strip())
    cleaned = re.sub(r'\s+', " ", cleaned)
    return (cleaned[:max_len] or "student").strip()


def render_student_docx(student: dict, dest: str, quiz_title: str = "New Quiz") -> str:
    """Write one student's portfolio section for a single quiz to `dest`. Returns dest."""
    doc = Document()
    doc.add_heading(student.get("name", "Student"), level=0)

    meta = []
    if student.get("section"):
        meta.append(student["section"])
    if student.get("submitted"):
        meta.append(student["submitted"][:10])
    meta.append(f"generated {datetime.now():%b %d, %Y}")
    doc.add_paragraph(" · ".join(meta))

    doc.add_heading(quiz_title, level=1)

    # Multiple-choice performance summary (context, not writing).
    score = student.get("overall_score")
    poss = student.get("points_possible")
    summary = doc.add_table(rows=1, cols=4)
    summary.style = "Light Grid Accent 1"
    hdr = ["Score", "Correct (MC)", "Incorrect (MC)", "No response"]
    for i, h in enumerate(hdr):
        summary.rows[0].cells[i].text = h
    cells = summary.add_row().cells
    cells[0].text = f"{score:g}/{poss:g}" if score is not None and poss is not None else ""
    cells[1].text = str(student.get("num_correct") if student.get("num_correct") is not None else "")
    cells[2].text = str(student.get("num_incorrect") if student.get("num_incorrect") is not None else "")
    cells[3].text = str(student.get("no_response") if student.get("no_response") is not None else "")

    # Constructed (written) responses — the portfolio core.
    written = constructed_responses(student)
    doc.add_heading("Written responses", level=2)
    if not written:
        doc.add_paragraph("No written responses on this quiz.")
    for it in written:
        doc.add_heading(it.get("prompt") or "(untitled prompt)", level=3)
        body = html_to_text(it.get("response", ""))
        if body:
            for para in body.split("\n\n"):
                doc.add_paragraph(para)
        else:
            doc.add_paragraph("(no response)")
        ep = it.get("earned_points")
        if ep is not None:
            doc.add_paragraph(f"Points earned: {ep:g}").italic = True

    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    doc.save(dest)
    return dest


def render_portfolio(parsed: dict, out_dir: str, quiz_title: str = "New Quiz") -> list:
    """Render one DOCX per student from a parsed student_analysis dict.
    Returns the list of written file paths. `out_dir` must be outside the repo."""
    written = []
    for student in parsed.get("students", []):
        stem = _safe(student.get("name", "student"))
        dest = os.path.join(out_dir, f"{stem} - {_safe(quiz_title)}.docx")
        written.append(render_student_docx(student, dest, quiz_title))
    return written
