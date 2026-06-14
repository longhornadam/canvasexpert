"""Lightweight JSON syntax linter and best-effort repairer.

lint_json_syntax: scans for multiple obvious syntax errors so authors get
more than the first decode error.

repair_json: attempts to fix the most common LLM JSON mistakes (trailing
commas, JS-style comments, single-quoted strings) before giving up.
"""

from __future__ import annotations

import re
from typing import List, Tuple


def _line_col_from_index(raw: str, index: int) -> Tuple[int, int]:
    """Return 1-based (line, col) for a character index."""
    line = raw.count("\n", 0, index) + 1
    last_nl = raw.rfind("\n", 0, index)
    col = index - last_nl
    return line, col


def lint_json_syntax(raw: str, max_errors: int = 5) -> List[str]:
    """Scan JSON text for common syntax issues without stopping at the first.

    Returns a list of human-readable error strings (up to max_errors).
    """
    errors: List[str] = []
    stack = []
    pos = 0
    line = 1
    col = 0
    length = len(raw)

    def add_error(msg: str) -> None:
        if len(errors) < max_errors:
            errors.append(msg)

    def next_non_space(start: int, start_line: int, start_col: int):
        """Find the next non-whitespace character and its position info."""
        l, c = start_line, start_col
        p = start
        while p < length:
            ch = raw[p]
            if ch == "\n":
                l += 1
                c = 0
            else:
                c += 1
            if not ch.isspace():
                return ch, p, l, c
            p += 1
        return None, length, l, c

    while pos < length and len(errors) < max_errors:
        ch = raw[pos]
        if ch == "\n":
            line += 1
            col = 0
            pos += 1
            continue
        if ch.isspace():
            col += 1
            pos += 1
            continue

        # Strings (with basic escape handling)
        if ch == '"':
            start_line, start_col = line, col + 1
            pos += 1
            col += 1
            escaped = False
            while pos < length:
                ch = raw[pos]
                if ch == "\n":
                    line += 1
                    col = 0
                else:
                    col += 1
                if escaped:
                    escaped = False
                    pos += 1
                    continue
                if ch == "\\":
                    escaped = True
                    pos += 1
                    continue
                if ch == '"':
                    pos += 1
                    break
                pos += 1
            else:
                add_error(
                    f"Unterminated string starting near line {start_line}, column {start_col}; check for an unescaped quote or missing closing quote."
                )
                break

            # After a string token, ensure next significant char is valid (comma/colon/close/end)
            end_line, end_col = line, col
            next_char, next_pos, next_line, next_col = next_non_space(pos, line, col)
            if next_char is not None and next_char not in {",", ":", "}", "]"}:
                add_error(
                    f"String ending at line {end_line}, column {end_col} is followed by '{next_char}' (line {next_line}, column {next_col}) without a comma/colon; likely a missing comma or an unescaped quote inside the string."
                )
            pos = next_pos
            line, col = next_line, next_col
            continue

        # Structural tokens
        if ch in "{[":
            stack.append((ch, line, col + 1))
            pos += 1
            col += 1
            continue
        if ch in ":,":
            pos += 1
            col += 1
            continue
        if ch in "}]":
            if not stack:
                add_error(f"Unexpected closing '{ch}' at line {line}, column {col + 1}; no matching opener.")
            else:
                opener, opener_line, opener_col = stack.pop()
                if opener == "{" and ch != "}":
                    add_error(
                        f"Mismatched closing '{ch}' at line {line}, column {col + 1}; expected '}}' for opener '{{' at line {opener_line}, column {opener_col}."
                    )
                elif opener == "[" and ch != "]":
                    add_error(
                        f"Mismatched closing '{ch}' at line {line}, column {col + 1}; expected ']' for opener '[' at line {opener_line}, column {opener_col}."
                    )
            pos += 1
            col += 1
            continue

        # Numbers and literals (minimal handling just to advance)
        if ch.isdigit() or ch == "-":
            start_line, start_col = line, col + 1
            while pos < length and raw[pos] not in " \t\r\n,}]":
                if raw[pos] == "\n":
                    line += 1
                    col = 0
                else:
                    col += 1
                pos += 1
            next_char, next_pos, next_line, next_col = next_non_space(pos, line, col)
            if next_char is not None and next_char not in {",", "}", "]"}:
                add_error(
                    f"Number starting near line {start_line}, column {start_col} is followed by '{next_char}' without a comma; check for a missing comma."
                )
            pos = next_pos
            line, col = next_line, next_col
            continue

        if raw.startswith("true", pos):
            pos += 4
            col += 4
            continue
        if raw.startswith("false", pos):
            pos += 5
            col += 5
            continue
        if raw.startswith("null", pos):
            pos += 4
            col += 4
            continue

        # Unknown token
        add_error(f"Invalid token '{ch}' at line {line}, column {col + 1}; not valid JSON syntax.")
        # Skip ahead to the next likely structural boundary to avoid cascading noise
        pos += 1
        col += 1
        while pos < length and raw[pos] not in {",", "}", "]", "{", "[", "\n"}:
            if raw[pos] == "\n":
                line += 1
                col = 0
            else:
                col += 1
            pos += 1

    if len(errors) < max_errors and stack:
        for opener, opener_line, opener_col in reversed(stack):
            if len(errors) >= max_errors:
                break
            expected = "}" if opener == "{" else "]"
            add_error(f"Unclosed '{opener}' opened at line {opener_line}, column {opener_col}; add matching '{expected}'.")

    # Heuristic hint: unescaped inner quotes like ""interpreter"
    if len(errors) < max_errors:
        for match in re.finditer(r'"(?P<field>[^"]+)"\s*:\s*""(?P<word>[^"\\\s])', raw):
            if len(errors) >= max_errors:
                break
            idx = match.start(0)
            line_num, col_num = _line_col_from_index(raw, idx)
            field = match.group("field")
            add_error(
                f"Unescaped quote likely in field '{field}' near line {line_num}, column {col_num}; escape inner quotes as \\\"...\\\"."
            )

    return errors[:max_errors]


def repair_json(raw: str) -> str:
    """Attempt to fix common LLM JSON mistakes before parsing.

    Handles:
    - Single-quoted string delimiters  ({'key': 'val'} → {"key": "val"})
    - JS-style // line comments and /* block comments
    - Trailing commas before } or ]

    Returns the repaired string. If the repair logic itself raises, returns
    the original string unchanged so the caller can still produce a useful
    error message.
    """
    try:
        return _do_repair(raw)
    except Exception:
        return raw


def _do_repair(raw: str) -> str:
    out: List[str] = []
    i = 0
    n = len(raw)

    while i < n:
        ch = raw[i]

        # ── String token (double- or single-quoted) ──────────────────────────
        if ch in ('"', "'"):
            quote = ch
            out.append('"')
            i += 1
            while i < n:
                c = raw[i]
                if c == '\\':
                    if quote == '"':
                        # Honour existing escapes in double-quoted strings verbatim.
                        out.append(c)
                        i += 1
                        if i < n:
                            out.append(raw[i])
                            i += 1
                    else:
                        # Single-quoted: only \\ and \' are meaningful escapes.
                        if i + 1 < n and raw[i + 1] == "'":
                            out.append("'")  # \' → literal '
                            i += 2
                        elif i + 1 < n and raw[i + 1] == '\\':
                            out.append('\\\\')
                            i += 2
                        else:
                            out.append(c)
                            i += 1
                elif c == '"' and quote == "'":
                    out.append('\\"')  # double-quote inside single-quoted → escape it
                    i += 1
                elif c == quote:
                    out.append('"')
                    i += 1
                    break
                else:
                    out.append(c)
                    i += 1
            continue

        # ── JS // line comment ────────────────────────────────────────────────
        if ch == '/' and i + 1 < n and raw[i + 1] == '/':
            while i < n and raw[i] != '\n':
                i += 1
            continue

        # ── JS /* block comment */ ────────────────────────────────────────────
        if ch == '/' and i + 1 < n and raw[i + 1] == '*':
            i += 2
            while i < n:
                if raw[i] == '*' and i + 1 < n and raw[i + 1] == '/':
                    i += 2
                    break
                i += 1
            continue

        out.append(ch)
        i += 1

    repaired = ''.join(out)
    # Remove trailing commas immediately before } or ] (handles arrays and objects).
    repaired = re.sub(r',(\s*[}\]])', r'\1', repaired)
    return repaired
