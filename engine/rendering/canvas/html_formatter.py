"""HTML helpers used by the QTI renderer."""

from __future__ import annotations

import re
from typing import Optional
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

from .code_formatting import (
    _wrap_code_block,
    apply_syntax_highlighting_to_html,
    syntax_highlight_python,
    transform_code_blocks,
)
from .passage_numbering import _analyze_passage_content, add_passage_numbering
from .text_cleaning import (
    _clean_code_content,
    _clean_text,
    _clean_text_executable,
    _clean_text_verbatim,
)


def sanitize_for_canvas(text: str) -> str:
    """Sanitize text for Canvas compatibility.
    
    This is a comprehensive sanitization function that:
    1. Cleans escaped sequences (\\n → newline)
    2. Transforms code blocks to HTML
    3. Ensures no problematic characters remain
    
    Use this for any text that will be displayed in Canvas.
    
    Args:
        text: Raw text that may contain Markdown
        
    Returns:
        Canvas-safe HTML text
    """
    if not text:
        return text
    
    # Default to executable here (this helper is explicitly for Canvas display cleanup).
    result = _clean_text(text, render_mode="executable")
    
    # Then transform code blocks
    result = transform_code_blocks(result, render_mode="executable")
    
    return result


# Special marker removed - Canvas expects escaped HTML in XML


def html_mattext(text: str) -> ET.Element:
    """Create a mattext element with HTML content.
    
    Canvas expects HTML to be escaped in the XML (e.g., &lt;p&gt; not <p>).
    ElementTree's default behavior handles this correctly.
    """
    element = ET.Element("mattext", {"texttype": "text/html"})
    element.text = text
    return element


def serialize_element(element: ET.Element) -> str:
    """Serialize an ElementTree element to XML string.
    
    Uses standard ElementTree serialization which properly escapes
    HTML content (Canvas expects &lt;p&gt; not <p> in mattext elements).
    """
    return ET.tostring(element, encoding="utf-8").decode("utf-8")


def htmlize_prompt(text: str, *, excerpt_numbering: bool = True, render_mode: str = "verbatim") -> str:
    original_text = text
    mode = (render_mode or "verbatim").lower() if isinstance(render_mode, str) else "verbatim"
    if mode != "executable":
        if original_text != text or len(original_text) != len(text):
            raise ValueError("Verbatim render_mode mutated student-facing text during formatting.")
        return text

    # Executable: allow escape interpretation and formatting
    text = _clean_text(text, render_mode="executable")
    
    if re.search(r"<\w+[^>]*>", text):
        # HTML is already present - apply syntax highlighting to code blocks
        text = apply_syntax_highlighting_to_html(text)
        return text

    monokai_style = (
        "background-color: #272822; "
        "color: #F8F8F2; "
        "padding: 10px; "
        "border-radius: 4px; "
        "font-family: 'Courier New', Consolas, monospace; "
        "overflow-x: auto; "
        "line-height: 1.5;"
    )

    lines = text.split("\n")
    html_parts: list[str] = []
    index = 0

    def esc(value: str) -> str:
        return xml_escape(value)

    def render_excerpt_block(content: str, forced_type: Optional[str] = None) -> str:
        if not excerpt_numbering:
            forced_type = "none"
        numbered_content, passage_type = add_passage_numbering(content, forced_type or "auto")

        import re as _re

        def style_numbers(value: str) -> str:
            num_style = "font-size: 0.85em; font-style: italic; color: #999; font-weight: normal;"
            value = _re.sub(r"\{LINENUM:(\s*\d+)\}", lambda m: f'<span style="{num_style}">{m.group(1)}</span>', value)
            value = _re.sub(r"\{PARANUM:(\d+)\}", lambda m: f'<span style="{num_style}">[{m.group(1)}]</span>', value)
            return value

        styled = style_numbers(numbered_content)

        if passage_type == "poetry":
            lines_html = styled.split("\n")
            line_html = []
            for line in lines_html:
                if line.strip():
                    escaped = esc(line)
                    escaped = re.sub(r'&lt;span style=\"([^\"]*)\"&gt;', r'<span style="\1">', escaped)
                    escaped = escaped.replace("&lt;/span&gt;", "</span>")
                    line_html.append(f'<div style="margin: 0; padding: 0; line-height: 1.6;">{escaped}</div>')
                else:
                    line_html.append('<div style="margin: 0; padding: 0; line-height: 1.6;">&nbsp;</div>')
            return (
                '<div style="margin:10px 0;">'
                '<div style="font-family: inherit; font-size:0.95em; padding:14px 18px; background:#fff; border:1px solid #d9d9d9; border-left:5px solid #4b79ff; '
                'line-height:1.6;">'
                + "".join(line_html)
                + "</div></div>"
            )
        if passage_type in {"prose_short", "prose_long", "prose"}:
            paragraphs = styled.split("\n\n")
            para_html = []
            for paragraph in paragraphs:
                if paragraph.strip():
                    escaped = esc(paragraph)
                    escaped = re.sub(r'&lt;span style=\"([^\"]*)\"&gt;', r'<span style="\1">', escaped)
                    escaped = escaped.replace("&lt;/span&gt;", "</span>")
                    para_html.append(f'<p style="margin: 0 0 0.9em 0; line-height: 1.6;">{escaped}</p>')
            return (
                '<div style="margin:10px 0;">'
                '<div style="font-family: inherit; font-size:0.95em; padding:14px 18px; background:#fff; border:1px solid #d9d9d9; border-left:5px solid #4b79ff; '
                'line-height:1.6;">'
                + "".join(para_html)
                + "</div></div>"
            )
        return (
            '<div style="margin:10px 0;">'
            '<div style="font-family: inherit; font-size:0.95em; padding:14px 18px; background:#fff; border:1px solid #d9d9d9; border-left:5px solid #4b79ff; '
            'line-height:1.6; white-space:pre-wrap;">' + esc(numbered_content) + '</div></div>'
        )

    # If excerpt_numbering is enabled and no special blocks detected, treat as excerpt block
    has_code_fences = "```" in text
    has_excerpt_blocks = ">>>" in text
    has_headings = re.search(r"^#{1,6}\s+", text, re.MULTILINE)
    
    if excerpt_numbering and not (has_code_fences or has_excerpt_blocks or has_headings):
        # Treat entire text as excerpt block
        return render_excerpt_block(text)

    while index < len(lines):
        line = lines[index]
        heading = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if heading:
            level = min(len(heading.group(1)), 3)
            html_parts.append(f"<h{level}>{esc(heading.group(2).strip())}</h{level}>")
            index += 1
            continue

        if line.strip().startswith("```"):
            fence = line.strip()
            lang = fence[3:].strip()
            index += 1
            block: list[str] = []
            while index < len(lines):
                current_line = lines[index]
                # Check if this line ends with closing backticks
                if current_line.strip().endswith("```") and not current_line.strip().startswith("```"):
                    # Line ends with ```, strip them and add the code part
                    code_part = current_line.rstrip()[:-3]
                    if code_part.strip():
                        block.append(code_part)
                    index += 1
                    break
                # Check if line starts with closing backticks
                if current_line.strip().startswith("```"):
                    index += 1
                    break
                block.append(current_line)
                index += 1
            code = "\n".join(block)
            lang_lower = (lang or "").lower()
            if lang_lower in {"excerpt", "prose", "poetry"}:
                if lang_lower == "poetry":
                    forced = "poetry"
                else:
                    forced = "prose"
                html_parts.append(render_excerpt_block(code, forced_type=forced))
            elif lang_lower == "python":
                highlighted = syntax_highlight_python(code)
                html_parts.append(f"<pre style=\"{monokai_style}\"><code class=\"language-{esc(lang)}\">{highlighted}</code></pre>")
            else:
                html_parts.append(f"<pre style=\"{monokai_style}\"><code class=\"language-{esc(lang)}\">{esc(code)}</code></pre>")
            continue

        if line.strip() == ">>>":
            index += 1
            block: list[str] = []
            while index < len(lines) and lines[index].strip() != ">>>":
                block.append(lines[index])
                index += 1
            if index < len(lines) and lines[index].strip() == ">>>":
                index += 1
            html_parts.append(render_excerpt_block("\n".join(block)))
            continue

        if line.startswith("> "):
            block = [line[2:]]
            index += 1
            while index < len(lines) and lines[index].startswith("> "):
                block.append(lines[index][2:])
                index += 1
            html_parts.append("<blockquote>" + "<br/>".join(esc(item) for item in block) + "</blockquote>")
            continue

        paragraph: list[str] = []
        while index < len(lines) and lines[index].strip() != "":
            if lines[index].strip().startswith("```") or lines[index].strip() == ">>>" or lines[index].startswith("> "):
                break
            paragraph.append(lines[index])
            index += 1
        if index < len(lines) and lines[index].strip() == "":
            while index < len(lines) and lines[index].strip() == "":
                index += 1
        if paragraph:
            joined = "\n".join(paragraph)
            if not excerpt_numbering:
                quote_match = re.search(r'"([^"\n]{40,})"|\u201c([^\u201d\n]{40,})\u201d', joined)
                if quote_match:
                    quoted = quote_match.group(1) or quote_match.group(2) or ""
                    pre = joined[: quote_match.start()].strip()
                    post = joined[quote_match.end() :].strip()
                    if pre:
                        escaped_pre = esc(pre)
                        escaped_pre = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", escaped_pre)
                        html_parts.append(f"<p>{escaped_pre}</p>")
                    html_parts.append(
                        '<div style="margin:10px 0;"><div style="font-family: inherit; font-size:0.95em; padding:14px 18px; background:#fff; border:1px solid #d9d9d9; border-left:5px solid #4b79ff; line-height:1.6;">'
                        + esc(quoted)
                        + "</div></div>"
                    )
                    if post:
                        escaped_post = esc(post)
                        escaped_post = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", escaped_post)
                        html_parts.append(f"<p>{escaped_post}</p>")
                    continue
            escaped = esc(joined)
            escaped = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", escaped)
            html_parts.append(f"<p>{escaped}</p>")
        else:
            html_parts.append("<p></p>")

    return "\n".join(part for part in html_parts if part) or "<p></p>"


def htmlize_choice(text: str, *, render_mode: str = "verbatim") -> str:
    """Convert choice text to Canvas-safe HTML.
    
    Handles:
    - Fenced code blocks (```python ... ```) → <pre><code>...</code></pre>
    - Inline backticks (`code`) → <code>code</code>
    - Escaped newlines and HTML entities
    
    Args:
        text: Raw choice text that may contain Markdown code
        
    Returns:
        Canvas-safe HTML wrapped in <p> tags (unless it's a code block)
    """
    original_text = text
    mode = (render_mode or "verbatim").lower() if isinstance(render_mode, str) else "verbatim"
    if mode != "executable":
        if original_text != text or len(original_text) != len(text):
            raise ValueError("Verbatim render_mode mutated student-facing text during formatting.")
        return text or ""

    if not text:
        return "<p></p>"

    text = _clean_text(text, render_mode="executable")
    
    # Check if text contains fenced code blocks
    if '```' in text:
        # Use the full transformer for complex content
        transformed = transform_code_blocks(text, render_mode=render_mode)
        # If the entire choice is a code block, don't wrap in <p>
        if transformed.strip().startswith('<pre'):
            return transformed
        # Mixed content - wrap non-code parts
        return transformed
    
    # Simple case: only inline code or plain text
    def esc(value: str) -> str:
        return xml_escape(value)
    
    # Handle inline backticks
    def replace_inline(match: re.Match) -> str:
        code = match.group(1)
        # Clean up the code content
        code = _clean_code_content(code, render_mode=render_mode)
        return f"<code>{esc(code)}</code>"
    
    processed = re.sub(r"`([^`]+)`", replace_inline, text)
    
    # Escape the rest and wrap in paragraph
    # But preserve any <code> tags we just inserted
    parts = re.split(r'(<code>.*?</code>)', processed)
    result_parts = []
    for part in parts:
        if part.startswith('<code>'):
            result_parts.append(part)
        else:
            result_parts.append(esc(part))
    
    return f"<p>{''.join(result_parts)}</p>"

def htmlize_item_text(text: str, *, render_mode: str = "verbatim") -> str:
    """Convert item text (ordering, categorization, matching) to Canvas-safe HTML.
    
    Similar to htmlize_choice but returns just the transformed content
    without paragraph wrapper for flexibility.
    
    Args:
        text: Raw item text that may contain Markdown code
        
    Returns:
        Canvas-safe HTML content (no outer <p> wrapper)
    """
    original_text = text
    mode = (render_mode or "verbatim").lower() if isinstance(render_mode, str) else "verbatim"
    if mode != "executable":
        if original_text != text or len(original_text) != len(text):
            raise ValueError("Verbatim render_mode mutated student-facing text during formatting.")
        return text or ""

    if not text:
        return ""

    text = _clean_text(text, render_mode="executable")
    
    # Check if text contains fenced code blocks
    if '```' in text:
        return transform_code_blocks(text, render_mode=render_mode)
    
    # Handle inline backticks
    def esc(value: str) -> str:
        return xml_escape(value)
    
    def replace_inline(match: re.Match) -> str:
        code = match.group(1)
        code = _clean_code_content(code, render_mode=render_mode)
        return f"<code>{esc(code)}</code>"
    
    processed = re.sub(r"`([^`]+)`", replace_inline, text)
    
    # Escape non-code parts
    parts = re.split(r'(<code>.*?</code>)', processed)
    result_parts = []
    for part in parts:
        if part.startswith('<code>'):
            result_parts.append(part)
        else:
            result_parts.append(esc(part))
    
    return ''.join(result_parts)


def plaintext_item_text(text: str, *, render_mode: str = "verbatim") -> str:
    """Convert item text to plain text, stripping Markdown code fences.
    
    Use this for question types where Canvas doesn't render HTML
    (e.g., categorization items).
    
    Args:
        text: Raw item text that may contain Markdown code fences
        
    Returns:
        Plain text with code fences removed
    """
    original_text = text
    mode = (render_mode or "verbatim").lower() if isinstance(render_mode, str) else "verbatim"
    if mode != "executable":
        if original_text != text or len(original_text) != len(text):
            raise ValueError("Verbatim render_mode mutated student-facing text during formatting.")
        return text or ""

    if not text:
        return ""

    text = _clean_text(text, render_mode="executable")
    
    # Remove fenced code blocks but keep the code content
    # Pattern: ```language\ncode\n``` or ```code```
    def strip_fence(match: re.Match) -> str:
        content = match.group(1)
        # Remove language identifier if present (first line)
        lines = content.split('\n')
        if lines and lines[0].strip().isalpha():
            # First line looks like a language identifier
            lines = lines[1:]
        return '\n'.join(lines).strip()
    
    # Match fenced code blocks: ```...```
    text = re.sub(r'```([^`]*?)```', strip_fence, text, flags=re.DOTALL)
    
    # Handle inline backticks - just remove them
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    return text.strip()
