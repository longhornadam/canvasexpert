"""Text processing utilities shared across modules."""

import re
import uuid

_BAD_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_WINDOWS_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_filename_component(value, max_len: int = 120, fallback: str = "_unnamed") -> str:
    """Return a readable Windows/POSIX-safe filename or folder-name component.

    Replaces characters illegal on Windows, collapses whitespace, and guards
    reserved device names (CON, PRN, ...). This is the one shared sanitizer
    for teacher-visible names across the app -- reuse it rather than adding
    another variant.
    """
    text = _BAD_FILENAME_CHARS.sub("_", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip(" .")
    if not text:
        text = fallback
    text = text[:max(1, int(max_len))].rstrip(" .") or fallback
    if text.upper().split(".", 1)[0] in _RESERVED_WINDOWS_NAMES:
        text += "_"
    return text


def rand8() -> str:
    """Return an 8-character hex string for lightweight identifiers.
    
    Returns:
        8-character hex string
    """
    return uuid.uuid4().hex[:8]


def sanitize_text(value: str) -> str:
    """Normalize author-provided text to Canvas-safe ASCII characters.
    
    Replaces smart quotes, em dashes, and other Unicode characters
    with ASCII equivalents.
    
    Args:
        value: Text to sanitize
        
    Returns:
        Sanitized text with ASCII characters
    """
    if not value:
        return value
    
    mapping = {
        "\u201c": '"',  # Left double quote
        "\u201d": '"',  # Right double quote
        "\u2018": "'",  # Left single quote
        "\u2019": "'",  # Right single quote
        "\u2014": "-",  # Em dash
        "\u2013": "-",  # En dash
        "\u2026": "...",  # Ellipsis
        "\u00a0": " ",  # Non-breaking space
    }
    
    sanitized = value
    for bad, good in mapping.items():
        sanitized = sanitized.replace(bad, good)
    return sanitized


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace (remove extra spaces, trailing spaces).
    
    Args:
        text: Text to normalize
        
    Returns:
        Normalized text
    """
    return " ".join(text.split())
