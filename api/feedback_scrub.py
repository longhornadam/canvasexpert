"""Scrub engine for feedback tools — roster-aware real-name removal from student
writing content before it leaves the machine.

Built around a token map from `vault.all_real_identifiers()`, collision-checked
against protected (literary) names. Biases hard to over-correction: a false scrub
is fine; a leaked real name is not.

Pure stdlib; offline-testable.
"""
import re

# Neutral placeholder for a real Canvas/SIS id found in free text. Ids carry no
# useful signal for feedback quality (unlike a name), so there's no "fake id"
# to substitute in; just remove it. Deliberately word-character-free: the scrub
# engine re-scans its own output, so a placeholder containing letters (e.g.
# "[id]") could be re-clobbered by a later shorter name/nickname rule whose
# token appears inside it. "[#]" has no word chars, so no \b-bounded rule can
# match within it.
ID_PLACEHOLDER = "[#]"

# Ids shorter than this are never real Canvas/SIS ids in practice; skipping
# them avoids pathological corruption from a stray 1-2 char match (e.g. a
# lone digit that happens to equal a truncated/blank id field).
_MIN_ID_SCRUB_LEN = 3

# Common English words that happen to look like names — collision hints only.
# These are never used to block scrubbing, just surfaced in find_collisions().
COMMON_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "about", "into", "over", "after",
    "all", "also", "am", "are", "as", "at", "be", "been", "being",
    "did", "do", "does", "done", "each", "few", "get", "got", "has",
    "had", "have", "her", "here", "hers", "him", "his", "how", "its",
    "just", "like", "may", "more", "most", "much", "my", "no", "not",
    "now", "once", "only", "other", "our", "out", "own", "per", "said",
    "same", "she", "should", "so", "some", "such", "than", "that",
    "the", "their", "them", "then", "there", "these", "they", "this",
    "those", "through", "too", "under", "very", "was", "way", "were",
    "what", "when", "where", "which", "while", "who", "will", "with",
    "would", "you", "your",
    # Common name-words that appear in writing
    "will", "rose", "summer", "may", "grace", "hope", "faith", "joy",
    "mark", "jack", "sam", "max", "leo", "ray", "roy", "earl",
    "page", "stone", "river", "lake", "forest", "brooke", "dale",
    "shelby", "sydney", "alexis", "morgan", "casey", "jordan", "taylor",
    "kelly", "skyler", "harley", "madison", "charlie",
    "king", "queen", "angel", "storm", "snow", "sunny", "olive",
}


def _tokenize(name: str) -> list[str]:
    """Split a full name into tokens (first, last, middle)."""
    return name.strip().split()


def build_replacement_map(vault_entries: list[dict],
                          protected: set[str]) -> list[tuple]:
    """Return [(compiled_regex, replacement)] for the WHOLE roster, sorted
    longest-token-first.

    Per student, map:
      - full real name -> full fake name
      - first name -> pseudo_first
      - last name -> pseudo_last
      - each nickname -> full pseudonym
      - canvas_id, sis_id (when >= _MIN_ID_SCRUB_LEN chars) -> ID_PLACEHOLDER

    A token that is ALSO in `protected` is STILL scrubbed (roster identity wins
    over a literary match — privacy first). `protected` only shields words that
    are NOT roster tokens.

    The returned rules are ordered by pattern length descending (longest match
    first) so 'Jose Flores' -> 'Sparky McGee' beats the single-token rules.
    """
    rules: list[tuple[str, str]] = []  # (regex_string, replacement)

    for entry in vault_entries:
        real_name = entry.get("real_name", "").strip()
        pseudo_first = entry.get("pseudo_first", "")
        pseudo_last = entry.get("pseudo_last", "")
        pseudo = entry.get("pseudonym", "")
        nicknames = entry.get("nicknames", [])

        # Real ids (canvas_id, sis_id) -> neutral placeholder. This runs
        # BEFORE the name/nickname guard below so an entry with no name on
        # file (or no nicknames) still gets its id scrubbed out of free text
        # — a student's Canvas/SIS number typed into an essay body is just as
        # much a real identifier as their name.
        for id_field in ("canvas_id", "sis_id"):
            raw_id = str(entry.get(id_field, "") or "").strip()
            if len(raw_id) >= _MIN_ID_SCRUB_LEN:
                rules.append((re.escape(raw_id), ID_PLACEHOLDER))

        if not real_name and not nicknames:
            continue

        # Full real name -> full pseudonym (e.g. "Jose Flores" -> "Sparky McGee")
        if real_name and pseudo:
            rules.append((re.escape(real_name), pseudo))

        # Individual tokens
        tokens = _tokenize(real_name)
        for i, token in enumerate(tokens):
            if not token:
                continue
            mapped = pseudo_first if i == 0 else (pseudo_last if i == len(tokens) - 1 else pseudo_first)
            if mapped:
                rules.append((re.escape(token), mapped))

        # Nicknames/aliases -> full pseudonym so every identity alias resolves
        # consistently to the student's existing pseudonym.
        for nn in nicknames:
            if nn.strip():
                rules.append((re.escape(nn.strip()), pseudo or pseudo_first))

    # Sort by pattern length descending (longest first) so full-name rules beat
    # single-token rules
    rules.sort(key=lambda r: len(r[0]), reverse=True)

    # Compile regexes with word boundaries, case-insensitive
    compiled = []
    for pattern_str, replacement in rules:
        try:
            compiled.append((
                re.compile(rf'\b{pattern_str}\b', re.IGNORECASE),
                replacement,
            ))
        except re.error:
            continue

    return compiled


def scrub_text(text: str, replacement_map: list[tuple]) -> str:
    """Apply the replacement map. Word-boundary, case-insensitive;
    possessives fall out naturally (\\bJose\\b matches in 'Jose's' -> 'Sparky's').
    Longest patterns first so 'Jose Flores'->'Sparky McGee' beats single-token rules.
    """
    result = text
    for regex, replacement in replacement_map:
        result = regex.sub(replacement, result)
    return result


def find_collisions(vault_entries: list[dict],
                    protected: set[str]) -> dict:
    """Return a dict of collision categories for the UI to surface:
    {
      'literary': [...real names that match a protected literary name...],
      'dup_first': [...first names shared by 2+ students...],
      'common_word': [...nickname/name tokens <=2 chars or in COMMON_WORDS...],
    }
    None of these block anything — they are informational only.
    """
    literary: list[str] = []
    dup_first: list[str] = []
    common_word: list[str] = []

    first_names: dict[str, list[str]] = {}
    protected_lower = {p.lower() for p in protected}

    for entry in vault_entries:
        real_name = entry.get("real_name", "").strip()
        tokens = _tokenize(real_name)
        nicknames = entry.get("nicknames", [])

        # Literary collision: real name (or any token) matches a protected name
        if real_name and real_name.lower() in protected_lower:
            literary.append(real_name)
        for token in tokens:
            if token.lower() in protected_lower and real_name not in literary:
                literary.append(f"{real_name} ('{token}')")
                break

        # Dup first names
        if tokens:
            fn = tokens[0].lower()
            first_names.setdefault(fn, []).append(real_name)

        # Common word tokens
        all_tokens = tokens + nicknames
        for t in all_tokens:
            t_lower = t.lower().strip(".'\"")
            if len(t_lower) <= 2 and t_lower not in ("i", "a"):
                common_word.append(f"'{t}' (from '{real_name}')")
            elif t_lower in COMMON_WORDS:
                common_word.append(f"'{t}' (from '{real_name}')")

    # Find duplicate first names
    for fn, names in first_names.items():
        if len(names) >= 2:
            dup_first.append(f"{', '.join(names)}")

    return {
        "literary": sorted(set(literary)),
        "dup_first": sorted(set(dup_first)),
        "common_word": sorted(set(common_word)),
    }


def verify_clean(text: str, vault) -> list[str]:
    """Re-scan scrubbed text for any surviving real identifier
    (vault.all_real_identifiers() names). Returns survivors.
    With over-correction this should be empty; a non-empty result is a BUG
    to log, never a user task."""
    names, _ids = vault.all_real_identifiers()
    survivors: list[str] = []
    text_lower = text.lower()
    for name in names:
        if not name:
            continue
        # Check word-boundary match for each token (case-insensitive)
        for token in name.split():
            if re.search(rf'\b{re.escape(token)}\b', text_lower, re.IGNORECASE):
                survivors.append(name)
                break
    return survivors
