"""Outbound PII safety scan — the gate before anything goes to an external LLM.

Two layers, by design (Hanlon's Razor: assume accidents, make leaks impossible-by-
default and obvious, without nagging):

  HARD (blocks send): the payload carries an identity-bearing field (name, canvas_id,
  sis_id, section, ...) or a known real id as a value. A correctly pseudonymized
  bundle has none of these; this catches a raw/un-pseudonymized payload reaching the
  send path at all. If hard violations exist, the UI shows RED and the send button
  stays disabled.

  SOFT (warns, review): a known roster name appears inside free-text (prompt/response).
  Kids write names in their writing; we can't auto-decide if it's a real person or a
  character, so we surface it for the teacher rather than blocking.

Pure stdlib; offline-testable. Verdict is GREEN only when there are zero hard violations.
"""

# Dict keys that must never appear in an outbound payload.
_FORBIDDEN_KEYS = {"name", "real_name", "canvas_id", "sis_id", "sisid",
                   "section", "sectionnames", "sectionids", "sectionsisids"}
# Free-text fields where a name is a soft flag, not a hard block.
_TEXT_FIELDS = {"prompt", "response", "feedback"}


def _walk(obj, path=""):
    """Yield (path, key, value) for every dict key in a nested structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield (path, k, v)
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def scan_payload(payload, vault) -> dict:
    """Scan an outbound payload against the vault.
    Returns {green: bool, hard: [str], soft: [dict]}."""
    names, ids = vault.all_real_identifiers()
    lowered_names = {n.lower(): n for n in names if n}
    hard, soft = [], []

    for path, key, value in _walk(payload):
        kl = key.lower()
        # Layer 1a: forbidden identity-bearing keys with a non-empty value.
        if kl in _FORBIDDEN_KEYS and value not in (None, "", [], {}):
            hard.append(f"identity field '{key}' present at {path or 'root'}")
            continue
        if not isinstance(value, str) or not value:
            continue
        if kl in _TEXT_FIELDS:
            # Layer 2: known roster name inside free text -> soft flag.
            t = value.lower()
            for low, original in lowered_names.items():
                if low in t:
                    soft.append({"where": f"{path}.{key}", "name": original})
        else:
            # Layer 1b: a known real id appearing as a structural value -> hard.
            if value in ids:
                hard.append(f"real id '{value}' present at {path}.{key}")

    return {"green": not hard, "hard": hard, "soft": soft}
