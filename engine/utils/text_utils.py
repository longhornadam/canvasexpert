"""Text processing utilities shared across modules."""

import uuid


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
