"""Render PrintDoc objects to the shared HTML substrate."""

from __future__ import annotations

import html
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from engine.rendering.physical.printdoc import PrintDoc

_ROOT = Path(__file__).resolve().parent
_TEMPLATE_DIR = _ROOT / "templates"
_CSS_PATH = _ROOT / "styles" / "print.css"


def render_html(printdoc: PrintDoc, *, variant: str) -> str:
    """Render a student quiz or answer key HTML document."""

    if variant not in {"quiz", "key"}:
        raise ValueError("variant must be 'quiz' or 'key'")

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(("html", "xml", "j2")),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["alpha"] = _alpha
    env.filters["poetry_lines"] = _poetry_lines
    env.filters["prose_blocks"] = _prose_blocks

    template_name = "quiz.html.j2" if variant == "quiz" else "answer_key.html.j2"
    template = env.get_template(template_name)
    return template.render(
        printdoc=printdoc,
        variant=variant,
        css_href=str(_CSS_PATH),
        inline_css=_CSS_PATH.read_text(encoding="utf-8"),
    )


def default_css_path() -> str:
    return str(_CSS_PATH)


def _alpha(index: int) -> str:
    return chr(65 + int(index))


def _poetry_lines(value: str) -> list[str]:
    cleaned = _strip_outer_paragraphs(value)
    return [line.strip() for line in cleaned.splitlines() if line.strip()]


def _prose_blocks(value: str) -> list[str]:
    value = value.strip()
    if not value:
        return []
    if re.search(r"<\s*(p|ol|ul|table|pre|blockquote|div)\b", value, re.IGNORECASE):
        return [value]
    return [f"<p>{html.escape(line.strip())}</p>" for line in value.splitlines() if line.strip()]


def _strip_outer_paragraphs(value: str) -> str:
    text = re.sub(r"</p\s*>\s*<p\s*>", "\n", value.strip(), flags=re.IGNORECASE)
    text = re.sub(r"^<p\s*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)
