"""Render-mode gated text cleaning for Canvas HTML rendering."""

from __future__ import annotations


def _clean_text_content(text: str) -> str:
    """DEPRECATED: escape-cleaning must be render-mode gated.

    This function remains for backwards compatibility but MUST NOT be used for
    student-facing verbatim strings. Use _clean_text(text, render_mode=...).
    """
    return _clean_text(text, render_mode="executable")


def _clean_text_verbatim(text: str) -> str:
    """Verbatim mode: treat text as opaque payload (no escape interpretation)."""
    return text


def _clean_text_executable(text: str) -> str:
    """Executable mode: interpret escape sequences except in code contexts."""
    if not text:
        return text

    import re

    protected_regions = []
    placeholder_prefix = "__PROTECTED_CODE_"

    def protect_region(match):
        idx = len(protected_regions)
        protected_regions.append(match.group(0))
        return f"{placeholder_prefix}{idx}__"

    text = re.sub(r"```[\s\S]*?```", protect_region, text)
    text = re.sub(r"`[^`]+`", protect_region, text)
    text = re.sub(r"<code[^>]*>[\s\S]*?</code>", protect_region, text, flags=re.IGNORECASE)
    text = re.sub(r"<pre[^>]*>[\s\S]*?</pre>", protect_region, text, flags=re.IGNORECASE)

    text = text.replace("\\\\n", "\n")
    text = text.replace("\\n", "\n")
    text = text.replace("\\t", "\t")

    for idx in reversed(range(len(protected_regions))):
        placeholder = f"{placeholder_prefix}{idx}__"
        text = text.replace(placeholder, protected_regions[idx])

    return text


def _clean_text(text: str, *, render_mode: str = "verbatim") -> str:
    """Render-mode gated cleaning.

    - verbatim: no-op (hard-assert no mutation)
    - executable: interpret escape sequences

    Missing/unknown render_mode is treated as verbatim.
    """
    original = text
    mode = (render_mode or "verbatim").lower() if isinstance(render_mode, str) else "verbatim"
    if mode != "executable":
        cleaned = _clean_text_verbatim(text)
        if original != cleaned or (original is not None and cleaned is not None and len(original) != len(cleaned)):
            raise ValueError("Verbatim render_mode mutated student-facing text during cleaning.")
        return cleaned

    return _clean_text_executable(text)


def _clean_code_content(code: str, *, render_mode: str = "verbatim") -> str:
    """Clean code content by fixing HTML entities without interpreting escapes."""
    code = code.replace("&lt;", "<")
    code = code.replace("&gt;", ">")
    code = code.replace("&amp;", "&")
    code = code.replace("&quot;", '"')
    code = code.replace("&#39;", "'")
    return code.strip()
