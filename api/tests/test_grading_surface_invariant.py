"""Single grading-surface invariant.

PowerGrader is the sole owner of scoring student work and AI feedback. The one
hard, machine-checkable edge of that ownership: only PowerGrader may write an
AI-feedback submission comment to Canvas (``comment[text_comment]``). Gradebook
tools may adjust ``posted_grade`` (curve, late penalty, extension) but never
write feedback.

See docs/reference/powergrader-scoring-map.md (Guardrails: single grading surface).
"""

from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]

# Directories whose Python files are allowed to write ``comment[text_comment]``.
ALLOWED_WRITER_DIRS = {"powergrader"}

# A payload-building write looks like ``{"text_comment": ...}`` / ``"text_comment":``.
# Reads (``.get("text_comment")``) do not carry the trailing colon and are ignored.
WRITE_MARKER = '"text_comment":'


def _feedback_comment_writers() -> set[str]:
    writers: set[str] = set()
    for path in API_ROOT.rglob("*.py"):
        rel = path.relative_to(API_ROOT)
        if "tests" in rel.parts or "__pycache__" in rel.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if WRITE_MARKER in text:
            writers.add(rel.as_posix())
    return writers


def test_only_powergrader_writes_feedback_comments():
    writers = _feedback_comment_writers()
    # Sanity: the marker must exist somewhere, or the check has silently rotted.
    assert writers, "no feedback-comment writer found; update WRITE_MARKER"
    offenders = sorted(
        w for w in writers
        if not any(part in ALLOWED_WRITER_DIRS for part in Path(w).parts)
    )
    assert not offenders, (
        "AI-feedback comments (comment[text_comment]) must be written only by "
        "PowerGrader. Offending modules: " + ", ".join(offenders)
    )
