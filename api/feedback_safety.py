"""Outbound PII safety scan — the gate before anything goes to an external LLM.

Two layers, by design (Hanlon's Razor: assume accidents, make leaks impossible-by-
default and obvious, without nagging):

  HARD (blocks send): the payload carries an identity-bearing field (name, canvas_id,
  sis_id, section, ...), a known real id as a structural value, or a known real id
  (>= _MIN_ID_HARD_BLOCK_LEN chars) appearing as a word-bounded token inside free
  text (a student typing their own id number into an essay body). A correctly
  pseudonymized bundle has none of these; this catches a raw/un-pseudonymized
  payload reaching the send path at all. If hard violations exist, the UI shows
  RED and the send button stays disabled.

  SOFT (warns, review): a known roster name appears inside free-text (prompt/response).
  Kids write names in their writing; we can't auto-decide if it's a real person or a
  character, so we surface it for the teacher rather than blocking.

  Ids shorter than _MIN_ID_HARD_BLOCK_LEN found in free text are NOT hard-blocked
  here (a coincidental short number like a year would false-positive too often);
  they are instead proactively scrubbed to a placeholder before this scan ever
  runs (see feedback_scrub._MIN_ID_SCRUB_LEN, a lower floor of 3).

Pure stdlib; offline-testable. Verdict is GREEN only when there are zero hard violations.
"""

import re

# Dict keys that must never appear in an outbound payload.
_FORBIDDEN_KEYS = {"name", "real_name", "canvas_id", "sis_id", "sisid",
                   "section", "sectionnames", "sectionids", "sectionsisids"}
# Free-text fields where a name is a soft flag, not a hard block.
#
# This set is field-name-keyed, so a payload carrying student writing under a
# name that is not listed here is not scanned at all -- it comes back green
# whatever is inside it. Any subsystem that adds a new free-text field must add
# it here too, or the gate silently stops covering it. The dailywriting entries
# below are the daily writing substrate's stored text and quoted evidence
# spans: names appear inside student writing, so a span quoted out of a
# submission is exactly as identity-bearing as a response body.
_TEXT_FIELDS = {"prompt", "response", "feedback", "text", "assignment_description",
                # daily writing substrate (api/dailywriting)
                "raw_text", "evidence_span", "claim_text", "next_focus",
                "student_facing_text", "prompt_text", "strong_text",
                "near_miss_text", "one_thing", "acknowledgment",
                "flag_detail",
                # Roster seating notes. ai_context_note is scrubbed before it
                # goes out; private_note is never emitted at all. Both are
                # listed anyway so that if either ever reaches a payload
                # unscrubbed, it registers as a scrub miss instead of passing
                # unscanned, which is what this set exists to prevent.
                "private_note", "ai_context_note"}

# A real id found as a `\b`-bounded token inside free text is only a HARD
# block at this length or longer. Below it, a coincidental short number (a
# year, a count, a page number a student typed in an essay) must not
# withhold an otherwise-legitimate read — those are scrub-only (see
# feedback_scrub._MIN_ID_SCRUB_LEN, which still catches them proactively).
_MIN_ID_HARD_BLOCK_LEN = 5


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

    # Precompiled once (not per field): known ids long enough to hard-block
    # when found as a `\b`-bounded token inside free text. Paired with the
    # original id string so a hit still yields "real id '<value>' present at
    # ..." — the exact message _sanitize_violation()/_REAL_ID_VIOLATION in
    # api/mcp_server/pseudonym.py expects, so the raw value still gets
    # stripped before reaching an MCP client.
    hard_id_patterns = [
        (real_id, re.compile(rf"\b{re.escape(real_id)}\b"))
        for real_id in ids if len(real_id) >= _MIN_ID_HARD_BLOCK_LEN
    ]

    for path, key, value in _walk(payload):
        kl = key.lower()
        # Layer 1a: forbidden identity-bearing keys with a non-empty value.
        if kl in _FORBIDDEN_KEYS and value not in (None, "", [], {}):
            hard.append(f"identity field '{key}' present at {path or 'root'}")
            continue
        if not isinstance(value, str) or not value:
            continue
        if kl in _TEXT_FIELDS:
            # Layer 2a: known roster name inside free text -> soft flag.
            t = value.lower()
            for low, original in lowered_names.items():
                if low in t:
                    soft.append({"where": f"{path}.{key}", "name": original})
            # Layer 2b: known real id (>= _MIN_ID_HARD_BLOCK_LEN chars) as a
            # word-bounded token inside free text -> hard block. Shorter ids
            # are scrub-only (Layer A in feedback_scrub) and never land here
            # as a hard violation, so a coincidental short number never
            # withholds a legitimate read.
            for real_id, pattern in hard_id_patterns:
                if pattern.search(value):
                    hard.append(f"real id '{real_id}' present at {path}.{key}")
        else:
            # Layer 1b: a known real id appearing as a structural value -> hard.
            if value in ids:
                hard.append(f"real id '{value}' present at {path}.{key}")

    return {"green": not hard, "hard": hard, "soft": soft}


def assert_scrubbed(payload, vault) -> dict:
    """Post-scrub safety receipt: scan_payload + return it. Intended to run AFTER
    scrubbing has been applied. 'green' must be True and 'soft' should be [];
    a non-empty 'soft' is logged as a scrub miss (bug), not surfaced to the user.
    Does not modify the payload or call save()."""
    verdict = scan_payload(payload, vault)
    # HARD must always be empty after scrubbing — this catches pipeline bugs.
    # SOFT should ideally be empty; non-empty means the scrub engine missed
    # a real identifier, which should be logged.
    return verdict
