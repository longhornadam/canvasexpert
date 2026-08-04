# Direct execution brief: PII barrier hardening, Batch 1 (A1, A2, A4, A6)

**Status:** Retired — GREEN; accepted 2026-08-03

**Executor:** senior (self-executed this session; guardrail/PII-adjacent code
stays in the Ferrari lane per the repo's Ferrari/Toyota convention)

**Senior objective:** Promote Batch 1 of
`docs/handoffs/senior level/feature-freeze-hardening-initiative.md` (baseline
`b8bb5e7`, re-confirmed clean at 2132 passed on 2026-08-03). Land the four
highest-risk, smallest-diff items in the two pure-stdlib PII modules, with no
UI surface: A1 (unicode-fold scrub and scan), A2 (token-level scan), A4
(close the forbidden-key gap), A6 (rename the misleading no-op assertion).

## Required context

Read `AGENTS.md`, then only these sections of the initiative document:
§1.1 (what the audit confirmed is sound), §2.1–2.3 (locked non-goals), §3
A1/A2/A4/A6 (the four items in scope), §7 (non-goals 1, 2, 5, 7), §8
(verification discipline), §9 (row 1 of the sequencing table).

Do not read §3 A3/A5/A7 or Batches B/C/D — out of scope for this brief.

## Locked decisions

**A1 — unicode folding.** Fold for matching only; the shipped scrub output
must remain byte-identical to the input outside a matched span (a fold
applied to the whole output would flatten legitimate accented words
elsewhere in a student's writing, which is worse than the defect being
fixed). This rules out "fold the whole text and ship the folded copy."

Implement in `api/feedback_scrub.py`:

```python
import unicodedata

def _fold(s: str) -> str:
    """NFKD-normalize and drop combining marks, for matching only."""
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))

def _fold_with_map(s: str) -> tuple[str, list[int]]:
    """Fold char-by-char; index_map[i] is the source index in `s` of
    folded[i]. Per-character (not whole-string) NFKD avoids cross-character
    decomposition surprises and keeps the offset map trivial to build."""
    folded_chars: list[str] = []
    index_map: list[int] = []
    for i, ch in enumerate(s):
        for fc in unicodedata.normalize("NFKD", ch):
            if not unicodedata.combining(fc):
                folded_chars.append(fc)
                index_map.append(i)
    return "".join(folded_chars), index_map
```

- `build_replacement_map`: fold every pattern source (the full `real_name`,
  each token, each nickname) before `re.escape` — i.e. compile from
  `re.escape(_fold(token))` instead of `re.escape(token)`. Do **not** fold
  `canvas_id`/`sis_id` patterns (ids carry no accents).
- `scrub_text`: patterns are now folded, so matching must run against a
  folded copy of the current `result`, then splice the replacement into the
  **original** `result` string at the mapped span, leaving everything
  outside matched spans untouched:

  ```python
  def scrub_text(text, replacement_map):
      result = text
      for regex, replacement in replacement_map:
          folded, index_map = _fold_with_map(result)
          matches = list(regex.finditer(folded))
          if not matches:
              continue
          pieces, last_end = [], 0
          for m in matches:
              start = index_map[m.start()]
              end = index_map[m.end() - 1] + 1 if m.end() > m.start() else start
              if start < last_end:
                  continue  # defensive: overlapping match, keep first
              pieces.append(result[last_end:start])
              pieces.append(replacement)
              last_end = end
          pieces.append(result[last_end:])
          result = "".join(pieces)
      return result
  ```

  This runs once per rule (same loop shape as today), each pass working off
  the previous pass's `result`, so byte-identical passthrough holds across
  the whole ordered rule list, not just within one rule.
- `find_token_matches(text, names) -> list[str]` (new, in
  `feedback_scrub.py`): per-token, folded, word-bounded, case-insensitive
  match against a set of full names — the single shared matcher for both
  `verify_clean` and the safety scan (see A2). Extract this from the existing
  per-token loop in `verify_clean` rather than writing new matching logic;
  `verify_clean` becomes a thin wrapper: `names, _ids =
  vault.all_real_identifiers(); return find_token_matches(text, names)`.
- `feedback_safety.scan_payload`: fold both sides of Layer 2a (`lowered_names`
  keys and the candidate text) via `_fold` before the substring check — or,
  once A2 lands, this layer is replaced entirely by `find_token_matches` (see
  below), which must itself fold both sides.
- Do not fold ids, and do not fold the `replacement` string (it is already
  the plain-ASCII pseudonym).

**A2 — token-level scan.** Replace `feedback_safety.scan_payload`'s Layer 2a
full-name substring check with a call to
`feedback_scrub.find_token_matches(value, names)`, appending one soft flag
per returned survivor name (same `{"where": ..., "name": original}` shape as
today — preserve original casing from the vault, not the folded/lowered
form). This mirrors the scrubber's own token granularity, per §3 A2, and
reuses `verify_clean`'s extracted logic per the initiative's explicit
instruction not to write a third matcher.

Expected consequence: soft-flag volume rises (single-token matches on common
given names now fire where only full-name matches fired before). This is
correct per §3 A2 and is not a regression; if an existing test's fixture
text now produces an unexpected soft flag, fix the fixture's data (pick a
name with no incidental token overlap) rather than suppressing the new
detection.

**Out of scope for this brief, do not touch:** A3 (denylist inversion — must
follow this brief, is Batch 2), A5 (soft-flag MCP disposition — explicitly
left open at §10 of the initiative doc; do not add a schema field, a
notice, or an operational-log emit for it here), A7, and anything in
Batches B/C/D.

**A4 — forbidden-key gap.** Add exactly these keys to
`api/mcp_server/pseudonym.py`'s gate-time `_FORBIDDEN_KEYS` (the set lives in
`api/feedback_safety.py`, imported/used by `gate()` via `scan_payload`):
`user_id`, `userid`, `student_id`, `sortable_name`, `short_name`, `login_id`,
`email`, `section_id`.

Pre-verified this session (senior-level check, not delegated) — none of the
7 `pseudonym.gate(...)` call sites in `api/mcp_server/tools.py` (lines ~408,
~1545, ~1827, ~1908, ~2019, ~2080, ~2205) place any of these 8 names as a key
in the gated payload for a non-identity purpose. In particular,
`list_sections`'s `{"section_id": ..., "section_name": ...}` row never
reaches `gate()` at all — the docstring says "No student data — no vault, no
safety gate" and the code confirms it never calls `pseudonym.gate`. The
executor does not need to re-audit this; if a new call site is found during
implementation that does use one of these 8 keys for a non-identity value,
stop and report YELLOW rather than silently excluding that key.

**A6 — rename the misleading no-op.** Rename
`api/dataforge/eduphoria_parser.py::assert_no_leaks` to
`scrub_or_passthrough`. No behavior change — same signature
`(text, anonymizer, artifact)`, same body (`if anonymizer is None: return
text`, else raise on detected leaks). Update all 3 call sites in the same
file (`convert_to_json`, `create_teacher_report`,
`create_parent_narratives`) and the one test that names the old function:
`api/tests/dataforge/test_identity_guardrails.py` — rename the import, the
test `test_assert_no_leaks_is_a_noop_without_a_provider` to
`test_scrub_or_passthrough_is_a_noop_without_a_provider`, and the module
docstring's reference to the old name. Do not invert the no-op into a raise;
the initiative document offers that as an alternative but "No behavior
change" is the binding constraint here.

## Authorized scope and insertion points

- `api/feedback_scrub.py`: `_fold`, `_fold_with_map`, `find_token_matches`,
  `build_replacement_map`, `scrub_text`, `verify_clean`.
- `api/feedback_safety.py`: `scan_payload` Layer 2a, and `_FORBIDDEN_KEYS`
  (the set lives here, not in `pseudonym.py` — `gate()` in
  `api/mcp_server/pseudonym.py` only calls `scan_payload`, it does not
  define the set).
- `api/dataforge/eduphoria_parser.py`: rename only, 3 call sites.
- `api/tests/test_feedback_scrub.py`, `api/tests/test_feedback_safety.py`,
  `api/tests/mcp_server/test_tools.py`,
  `api/tests/dataforge/test_identity_guardrails.py`: new/renamed tests per
  §8 of the initiative doc.
- Do not touch `api/webui/templates/assessments.html` (A7, Batch 5) or any
  file outside this list.

## Acceptance criteria

1. `José Flores` in the vault, `Jose helped me revise my thesis.` (unaccented
   given name only) as input to `scrub_text` no longer passes through
   unscrubbed — the given name is replaced.
2. `Renée Boudreaux` in the vault mapped so surname alone maps to a
   different-looking pseudonym than the given name would; `My partner Renee
   Boudreaux said the essay was strong.` scrubs to the full pseudonym, not a
   hybrid of a scrubbed surname and an unscrubbed given name.
3. A payload with a known roster name appearing as a single token (not the
   full name) inside a `_TEXT_FIELDS` value now produces a soft flag from
   `scan_payload`, where before only a full-name substring matched.
4. A payload carrying `sortable_name` (a name string) reaching
   `pseudonym.gate` is hard-blocked, same as `name` is today.
5. `scrub_or_passthrough(text, None, "x")` returns `text` unchanged;
   `eduphoria_parser.py` has no remaining reference to `assert_no_leaks`.
6. Scrubbed/scanned text with no accented characters is byte-identical to
   today's behavior (folding is a no-op on plain ASCII) — the existing
   `test_feedback_scrub.py`/`test_feedback_safety.py` suites pass unchanged
   in their assertions (fixture data may need a rename if a name now
   incidentally token-matches, per the A2 consequence note above, but the
   assertions' intent must not change).
7. No change to A3's denylist-vs-allowlist shape, A5's soft-flag
   disposition, A7's checkbox default, or any Batch B/C/D file.

## Named verification gate

```powershell
py -m pytest api/tests/test_feedback_scrub.py api/tests/test_feedback_safety.py api/tests/mcp_server/test_tools.py api/tests/dataforge/test_identity_guardrails.py api/tests/test_beta075_mcp.py api/tests/test_feedback_pipeline.py api/tests/test_vault_conflict.py api/tests/test_beta075_transmission.py api/tests/dailywriting -p no:randomly
```

Then the full gate:

```powershell
py -m pytest api/tests -q
```

Baseline is 2132 passed at `b8bb5e7`. This batch must add tests (net count
increases) and must not reduce the passing count.

## Stop conditions

Stop and report YELLOW/RED without guessing if: a `gate()` call site is
found using one of the 8 new forbidden keys for a non-identity value; folding
changes the output of any currently-passing byte-identical-outside-match
case; token-level scanning would require touching the hard-block layers
(Layer 1a/1b/2b) rather than only Layer 2a; or any change would require
touching `api/mcp_server/tool_schema_v*.json` (schema changes are out of
scope for this batch).

## Execution result

Traffic light: GREEN

Commit hash: recorded in the commit that includes this brief update.

Implemented all four items. `api/feedback_scrub.py` gained `_fold`,
`_fold_with_map`, and `find_token_matches`; `build_replacement_map` now
compiles patterns from folded name/nickname tokens (ids left unfolded) and
`scrub_text` matches on a folded copy of the text-so-far while splicing
replacements into the original string at mapped spans, so text outside a
match ships byte-identical. `verify_clean` is now a thin wrapper over
`find_token_matches`. `feedback_safety.scan_payload`'s Layer 2a calls the
same `find_token_matches`, replacing the old full-name-substring check, and
`_FORBIDDEN_KEYS` gained `user_id`, `userid`, `student_id`, `sortable_name`,
`short_name`, `login_id`, `email`, `section_id` after confirming none of the
7 `pseudonym.gate()` call sites in `api/mcp_server/tools.py` use these names
for a non-identity payload value (`list_sections`'s `section_id` never
reaches `gate()` at all — that tool has no vault/safety gate by design).
`eduphoria_parser.assert_no_leaks` was renamed to `scrub_or_passthrough`
with no behavior change across its 3 call sites and its one test.

Changed files:

- `api/feedback_scrub.py`
- `api/feedback_safety.py`
- `api/dataforge/eduphoria_parser.py`
- `api/tests/test_feedback_scrub.py` (+4 tests)
- `api/tests/test_feedback_safety.py` (+4 tests)
- `api/tests/dataforge/test_identity_guardrails.py` (rename only)
- `api/tests/dailywriting/test_dw_canvas_ingest.py` (1-line fixture fix, see
  deviations)
- this brief

Verification:

- Focused gate (`test_feedback_scrub.py test_feedback_safety.py
  mcp_server/test_tools.py dataforge/test_identity_guardrails.py
  test_beta075_mcp.py test_feedback_pipeline.py test_vault_conflict.py
  test_beta075_transmission.py dailywriting/ -p no:randomly`): 293 passed.
- Full gate (`py -m pytest api/tests -q`): 2140 passed (baseline 2132 + 8 new
  tests, 0 removed).
- Manual reproduction of both A1 doc cases (`Jose` unaccented pass-through;
  the `Renee Watts` hybrid) confirmed fixed, and a control case (`café`
  elsewhere in the text, unrelated to any roster name) confirmed
  byte-identical in the output.

Deviations: A2 raised soft-flag volume exactly as the initiative document
predicted (§3 A2 "Expected cost"). Two `test_dw_canvas_ingest.py` tests newly
soft-flagged on the word "one" inside the default fixture assignment
description ("Write one paragraph.") token-colliding with roster fixture
student "Learner One"'s surname. Per this brief's own guidance, fixed the
fixture (`description="Write a paragraph."`) rather than suppressing the new
detection; this is a local default in that one file only, not the
repo-wide "Learner One"/"Learner Two" naming convention used elsewhere.

Unresolved decisions: none for this brief. A3 (must follow this brief), A5
(soft-flag MCP disposition, left open at initiative §10), A7, and Batches
B/C/D remain as scoped in the initiative document.
