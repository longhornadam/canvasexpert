"""HTML rendering helpers for correction documents."""

from __future__ import annotations

from typing import Dict, Optional

from ...spec_engine.models import ChoiceRationale, PackagedQuiz, RationalesEntry
from .shared import _build_rationale_index, _choice_letter, _items_to_render, _strip_html
from .styles import (
    CORRECT_MARK_HEX,
    CORRECT_ROW_BG_HEX,
    HEADER_BG_HEX,
    HEADER_FG_HEX,
    INCORRECT_MARK_HEX,
    INCORRECT_ROW_BG_HEX,
    QUESTION_HDR_HEX,
    _FALLBACK_RATIONALE,
)


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_html_item(q_number: int, item: Dict, entry: RationalesEntry) -> str:
    prompt = item.get("prompt", "")
    header = f'<div class="question-header">Q{q_number}: {_escape_html(prompt)}</div>'

    if not entry.choices and getattr(entry, "text", None):
        qtype = item.get("type", "")
        label = "Model response to copy:" if qtype in ("ESSAY", "FILEUPLOAD") else "Explanation:"
        body = (
            f'<p class="single-rationale"><strong>{label}</strong> '
            f'{_escape_html(_strip_html(entry.text))}</p>'
        )
        return f'<div class="question-block">{header}{body}</div>'

    table = ""
    if entry.choices:
        choices_by_id = {c.id: c for c in entry.choices}
        item_choices = item.get("choices", [])

        rows_html = []
        for row_idx, choice_dict in enumerate(item_choices):
            letter = _choice_letter(choice_dict, row_idx)
            is_correct = bool(choice_dict.get("correct"))
            choice_text = choice_dict.get("text", "")
            cr: Optional[ChoiceRationale] = choices_by_id.get(letter)
            rationale_text = cr.rationale if cr else _FALLBACK_RATIONALE

            row_class = ' class="correct-row"' if is_correct else ' class="incorrect-row"'
            mark = "✓" if is_correct else "✗"
            mark_class = "correct-mark" if is_correct else "incorrect-mark"
            choice_class = "correct-choice" if is_correct else "incorrect-choice"
            rationale_class = "correct-text" if is_correct else "incorrect-text incorrect-rationale"

            rows_html.append(
                f'<tr{row_class}>'
                f'<td class="col-letter">{_escape_html(letter)}</td>'
                f'<td class="col-choice {choice_class}">{_escape_html(choice_text)}</td>'
                f'<td class="col-mark"><span class="{mark_class}">{mark}</span></td>'
                f'<td class="col-rationale {rationale_class}">{_escape_html(rationale_text)}</td>'
                f"</tr>"
            )

        table = (
            '<table class="rationale-table">'
            "<thead><tr>"
            '<th class="col-letter"></th>'
            '<th class="col-choice">Choice</th>'
            '<th class="col-mark">✓ / ✗</th>'
            '<th class="col-rationale">Rationale</th>'
            "</tr></thead>"
            "<tbody>"
            + "\n".join(rows_html)
            + "</tbody></table>"
        )

    return f'<div class="question-block">{header}{table}</div>'


def render_html_document(quiz: PackagedQuiz) -> str:
    rationale_index = _build_rationale_index(quiz.rationales)
    renderable = _items_to_render(quiz.items, rationale_index)
    has_choice_tables = any(entry.choices for _, _, entry in renderable)

    if renderable:
        body = "\n".join(
            _render_html_item(q_number, item, entry)
            for q_number, item, entry in renderable
        )
    else:
        body = (
            "<p><em>No per-choice rationales found. Check that the quiz was "
            "generated with the per-choice rationale format.</em></p>"
        )

    title = _escape_html(quiz.title or "Correction Document")
    table_css = ""
    if has_choice_tables:
        table_css = f"""
  table.rationale-table {{
    border-collapse: collapse;
    width: 100%;
    font-size: 10pt;
  }}
  table.rationale-table th,
  table.rationale-table td {{
    border: 1px solid #999;
    padding: 5px 7px;
    vertical-align: top;
  }}
  table.rationale-table thead tr {{
    background-color: #{HEADER_BG_HEX};
    color: #{HEADER_FG_HEX};
    font-weight: bold;
  }}
  table.rationale-table thead th {{
    border-color: #{HEADER_BG_HEX};
  }}
"""

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Correction Document</title>
<style>
  body {{
    font-family: Calibri, 'Segoe UI', Arial, sans-serif;
    font-size: 11pt;
    color: #111;
    margin: 1in 0.75in;
    line-height: 1.4;
  }}
  h1.doc-title {{
    color: #{HEADER_BG_HEX};
    font-size: 15pt;
    margin-bottom: 0.25em;
  }}
  p.doc-subtitle {{
    font-size: 10pt;
    color: #555;
    margin-top: 0;
    margin-bottom: 1.5em;
  }}
  .question-block {{
    margin-bottom: 1.5em;
  }}
  .question-header {{
    font-weight: bold;
    color: #{QUESTION_HDR_HEX};
    font-size: 11pt;
    margin-bottom: 0.4em;
  }}
  .col-letter   {{ width: 4%;  text-align: center; font-weight: bold; }}
  .col-choice   {{ width: 36%; }}
  .col-mark     {{ width: 5%;  text-align: center; font-weight: bold; }}
  .col-rationale{{ width: 55%; }}
  .correct-row  {{ background-color: #{CORRECT_ROW_BG_HEX}; }}
  .incorrect-row {{ background-color: #{INCORRECT_ROW_BG_HEX}; }}
  .correct-mark {{ color: #{CORRECT_MARK_HEX}; }}
  .incorrect-mark {{ color: #{INCORRECT_MARK_HEX}; }}
  .correct-choice {{ font-weight: bold; color: #{CORRECT_MARK_HEX}; }}
  .incorrect-choice {{ color: #{INCORRECT_MARK_HEX}; }}
  .correct-text {{ color: #{CORRECT_MARK_HEX}; }}
  .incorrect-text {{ color: #{INCORRECT_MARK_HEX}; font-style: italic; }}
  .incorrect-rationale {{ color: #{INCORRECT_MARK_HEX}; font-style: italic; }}
{table_css}\
</style>
</head>
<body>
<h1 class="doc-title">{title}</h1>
<p class="doc-subtitle">Correction Document — review each answer choice and its explanation.</p>
{body}
</body>
</html>
"""
