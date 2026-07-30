"""Code block transformation and syntax highlighting for Canvas HTML."""

from __future__ import annotations

import logging
import re
from xml.sax.saxutils import escape as xml_escape

from .text_cleaning import _clean_code_content

logger = logging.getLogger(__name__)


def transform_code_blocks(text: str, *, render_mode: str = "verbatim") -> str:
    """Transform Markdown code blocks to Canvas-safe HTML."""
    if not text:
        return text

    mode = (render_mode or "verbatim").lower() if isinstance(render_mode, str) else "verbatim"
    if mode != "executable":
        output_text = text
        if output_text != text or len(output_text) != len(text):
            raise ValueError("Verbatim render_mode mutated student-facing text during formatting.")
        return output_text

    if re.search(r"<pre>|<code>", text, re.IGNORECASE):
        return text

    result = text
    fenced_pattern = re.compile(r"```(\w*)\s*\n?(.*?)```", re.DOTALL)

    def replace_fenced(match: re.Match) -> str:
        lang = match.group(1).strip()
        code = _clean_code_content(match.group(2), render_mode=render_mode)

        if lang.lower() == "python":
            highlighted = syntax_highlight_python(code)
            return _wrap_code_block(highlighted, lang, highlighted=True)

        escaped_code = xml_escape(code)
        return _wrap_code_block(escaped_code, lang, highlighted=False)

    result = fenced_pattern.sub(replace_fenced, result)

    inline_pattern = re.compile(r"`([^`\n]+)`")

    def replace_inline(match: re.Match) -> str:
        code = _clean_code_content(match.group(1), render_mode=render_mode)
        escaped = xml_escape(code)
        return f"<code>{escaped}</code>"

    result = inline_pattern.sub(replace_inline, result)

    if "```" in result or "`" in result:
        logger.warning(
            "Backticks remain in text after code block transformation. "
            "This may cause rendering issues in Canvas."
        )

    return result


def _wrap_code_block(code: str, lang: str = "", highlighted: bool = False) -> str:
    """Wrap code in Canvas-safe <pre><code> tags with styling."""
    style = (
        "background-color: #272822; "
        "color: #F8F8F2; "
        "padding: 10px; "
        "border-radius: 4px; "
        "font-family: 'Courier New', Consolas, monospace; "
        "overflow-x: auto; "
        "line-height: 1.5; "
        "white-space: pre; "
        "display: block;"
    )

    lang_attr = f' class="language-{xml_escape(lang)}"' if lang else ""
    return f'<pre style="{style}"><code{lang_attr}>{code}</code></pre>'


def syntax_highlight_python(code: str) -> str:
    import re as _re

    keyword_color = "#F92672"
    function_color = "#A6E22E"
    string_color = "#E6DB74"
    comment_color = "#75715E"
    number_color = "#AE81FF"
    builtin_color = "#66D9EF"

    keywords = r"\b(def|class|if|elif|else|for|while|return|import|from|as|try|except|finally|with|lambda|yield|pass|break|continue|raise|assert|del|global|nonlocal|in|is|not|and|or|True|False|None)\b"

    result = xml_escape(code)
    result = _re.sub(r"(#[^\n]*)", f'<span style="color: {comment_color};">\\1</span>', result)
    result = _re.sub(
        r'(?<!span style="color: ' + comment_color + r';">)(["\'])(?:(?=(\\?))\2.)*?\1',
        lambda match: f'<span style="color: {string_color};">{match.group(0)}</span>',
        result,
    )
    result = _re.sub(r'(?<!span>)("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', f'<span style="color: {string_color};">\\1</span>', result)
    result = _re.sub(r"\b(\d+\.?\d*)\b", f'<span style="color: {number_color};">\\1</span>', result)
    result = _re.sub(
        r"\b(def)\s+(\w+)",
        f'<span style="color: {keyword_color};">\\1</span> <span style="color: {function_color};">\\2</span>',
        result,
    )
    result = _re.sub(r"\b(\w+)(?=\s*\()", f'<span style="color: {function_color};">\\1</span>', result)
    result = _re.sub(keywords, f'<span style="color: {keyword_color};">\\1</span>', result)
    builtins = r"\b(print|len|range|str|int|float|list|dict|set|tuple|input|open|enumerate|zip|map|filter|sorted|sum|min|max|abs|all|any|isinstance|type)\b"
    result = _re.sub(builtins, f'<span style="color: {builtin_color};">\\1</span>', result)

    return result


def apply_syntax_highlighting_to_html(html: str) -> str:
    """Apply Python syntax highlighting to <code> blocks within <pre> tags."""
    import re as _re

    def highlight_code_block(match):
        full_match = match.group(0)
        code_content = match.group(1)
        highlighted = syntax_highlight_python(code_content)
        pre_start = full_match[: full_match.index("<code>")]
        return f"{pre_start}<code>{highlighted}</code></pre>"

    pattern = r"<pre[^>]*>\s*<code[^>]*>(.*?)</code>\s*</pre>"
    return _re.sub(pattern, highlight_code_block, html, flags=_re.DOTALL)
