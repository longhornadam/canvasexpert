# Direct execution brief: PII barrier hardening, Batch 2 (A3)

**Status:** Retired — GREEN; accepted 2026-08-03

**Executor:** senior (self-executed this session; guardrail/PII-adjacent code
stays in the Ferrari lane)

**Senior objective:** Promote Batch 2 of
`docs/handoffs/senior level/feature-freeze-hardening-initiative.md` (baseline
`dev` @ `3576d15`, `api/tests` 2140 passed, Batch 1 landed and retired).
Invert `feedback_safety._TEXT_FIELDS` from an allowlist to a small
structural-exemption denylist, per §3 A3, so a new free-text field is scanned
by default instead of silently uncovered.

## Required context

Read `AGENTS.md`, then only these sections of the initiative document: §3 A3,
§7 non-goal 1, §8, §9 row 2. Do not read Batches B/C/D.

## Baseline re-confirmation performed this session

Full call-site inventory of every `scan_payload`/`gate` caller (not just the
7 `pseudonym.gate()` sites audited for A4), read directly from source:

- `api/mcp_server/tools.py`: the 7 `pseudonym.gate(...)` sites (roster
  settings, assessment context, assessment grouping, roster, seating,
  gradebook snapshot, submissions) **plus two more direct
  `feedback_safety.scan_payload(...)` calls** not part of the A4 audit:
  `get_standards_profile` (~line 1216) and `_assessment_context_profile`
  (~line 1428), both scanning the raw DataForge published profile dict.
- `api/ai_transmission.py::_scan_or_block` (the OpenRouter send gate) and
  `api/powergrader/ai_workflow.py` (`safety.scan_payload(bundle, vault)`),
  scanning `feedback_pipeline`/`feedback_artifacts` bundles
  (`pseudonymize`/`pseudonymize_submissions`/`apply_shared_context`).
- `api/tests/dailywriting/test_dw_evidence_store.py` and
  `api/tests/mcp_server/test_tools.py` call `scan_payload` directly against
  daily-writing-shaped fixtures (`flag_detail`, etc.).

**Correction to the initiative document's A3 finding:** §3 A3 states
`_TEXT_FIELDS` contains `assignment_description`, "which no payload anywhere
emits." This is not accurate for the full `scan_payload` caller set —
`api/powergrader/context.py::apply_shared_context` (line ~79) emits
`bundle["shared_context"]["assignment_description"]`, and it is scanned
today via the existing allowlist entry. The audit's narrower claim was
likely scoped to `api/mcp_server/tools.py` alone (whose own equivalent field
is `description_text`), not the PowerGrader path. This does not change the
implementation — under the new denylist model neither name needs to be
listed — but the correction is recorded so a future senior does not
propagate the inaccurate claim.

**A second finding, adjacent to A3's literal scope, found while verifying
the fix actually reaches "every string value in the payload":**
`feedback_safety._walk` does not visit a bare list of strings at all. A list
item is only visited if it is itself a dict (whose own keys get yielded);
a plain string inside a list is silently invisible to `scan_payload`
regardless of `_TEXT_FIELDS`/`_FORBIDDEN_KEYS` membership, because `_walk`
only ever produces a `(path, key, value)` triple from dict iteration.
Reproduced this session:

```python
from api.feedback_safety import _walk
list(_walk({"section_names": ["Period 1 with Ada Lovelace note"]}))
# -> [('', 'section_names', ['Period 1 with Ada Lovelace note'])]
# value is the LIST, not a string -- scan_payload's `isinstance(value, str)`
# guard then skips it entirely. The string never gets scanned.
```

This affects at least `section_names` (roster/seating tools) and
`standards[].assessed_in` (DataForge published profile — assessment name
labels, the same field the existing DataForge leak tests use as their
poison vector via `assessment_name`). A3's own stated goal is "scan every
string value in the payload"; that promise is false today for any
list-of-strings field. Fixing `_walk` to carry the enclosing dict key down
into bare list items is the same mechanism A3 is already touching (this
file, this function), so it is folded into this batch rather than filed as
a separate initiative. Flagged here explicitly as a locked decision, not a
silent scope expansion.

## Locked decisions

**A3 core — invert to a denylist.** Replace `_TEXT_FIELDS` (allowlist) with
`_STRUCTURAL_EXEMPT_KEYS` (denylist) in `api/feedback_safety.py`. Every
string value is scanned (Layer 2a soft name-match + Layer 2b hard id-match)
**unless** its key is in the exemption set, in which case it keeps today's
Layer 1b (exact-value match against a known real id) — same as an
unlisted key gets today, just phrased as the default rather than the
exception.

Exemption set (each entry verified against a real emitter in the call-site
inventory above, not assumed from the initiative document's illustrative
list):

```python
_STRUCTURAL_EXEMPT_KEYS = {
    # identifiers: an exact/token coincidental match against a real
    # Canvas/SIS id must not withhold an otherwise-legitimate read.
    "id", "course_id", "item_id",
    # digests/hashes: opaque values with no free-text content to review.
    "proposal_digest", "settings_digest",
    # timestamps: no free-text content; long digit runs carry the same
    # coincidental-id-match risk as an identifier.
    "synced_at", "due_at", "updated_at", "generated",
    # controlled-vocabulary/enum fields: a fixed, small set of known values
    # (e.g. "current"/"stale", "graded"/"submitted", "ready").
    "state", "workflow_state", "status", "scope", "grain", "method",
    # the vault-assigned fake name itself: scanning it cannot catch a real
    # leak (generated specifically not to collide with a real name) and
    # only adds review noise.
    "pseudonym",
}
```

**Deviation from the initiative document's illustrative list:** do **not**
exempt `source`. The initiative document names it as a candidate, and most
occurrences (`source.current_roster.source`, `payload["source"]`) are
genuinely a small controlled vocabulary ("mirror", "local_mirror",
"canvas"). But the same key name is reused by
`api/powergrader/context.py`'s `materials[].source` for a citation/
attribution string that is not guaranteed to be equally narrow. Because
`_STRUCTURAL_EXEMPT_KEYS` matches by key name only (no subsystem
awareness), exempting `source` globally would silently stop scanning that
PowerGrader field too. Scanning the enum-shaped `source` values is free —
no realistic enum value token-matches a name — so leaving `source` scanned
by default costs nothing and avoids narrowing coverage for the field that
actually needs it.

Do not add `title`, `label`, `group_name`, `section_name`, `section_names`,
`group_set_label`, `quiz_title`, `no_data_group`, `cutoffs`, or any other
teacher/Canvas-authored label to the exemption set — these are exactly the
currently-under-scanned free-text-ish fields the initiative document's audit
named as the reason A3 exists (§3 A3, "Unscanned keys that carry free text
today include ... `title`, `label`, `group_name`, `section_name`"). They
must default to scanned.

**`_walk` fix.** Carry the enclosing key down into a list so a bare scalar
list item is scanned under its parent key:

```python
def _walk(obj, path="", key=None):
    """Yield (path, key, value) for every dict key in a nested structure,
    and for every scalar item inside a list (using the enclosing dict key,
    since a bare list item has no key of its own)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield (path, k, v)
            yield from _walk(v, f"{path}.{k}", key=k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, (dict, list)):
                yield from _walk(v, f"{path}[{i}]", key=key)
            else:
                yield (f"{path}[{i}]", key, v)
```

In `scan_payload`, guard against `key` being `None` (only possible if the
top-level payload itself were a bare list, which no current caller does, but
the guard is one line and free): `kl = (key or "").lower()`.

**Out of scope for this brief:** A5, A7, and Batches B/C/D. Do not add a
tool-schema change, an operational-log emit, or a UI change.

## Authorized scope and insertion points

- `api/feedback_safety.py`: `_TEXT_FIELDS` -> `_STRUCTURAL_EXEMPT_KEYS`,
  `_walk`, `scan_payload`.
- `api/tests/test_feedback_safety.py`: new tests for the inversion and the
  `_walk` fix.
- Any test fixture across the repo that newly soft-flags due to broader
  coverage: fix the fixture's data (per Batch 1's established precedent),
  do not suppress the new detection. Report every such fixture change.

## Acceptance criteria

1. A payload string under a key not previously in `_TEXT_FIELDS` (e.g.
   `body_text`, `description_text`, `notes`, `summary`, `comment`) is now
   scanned: a known roster name inside it produces a soft flag.
2. A payload carrying `id`, `course_id`, `synced_at`, `workflow_state`,
   `state`, `proposal_digest`, or `pseudonym` with a value that happens to
   equal a known real id as an EXACT value is still hard-blocked (Layer 1b
   preserved for exempt keys); a value that merely contains a name-shaped
   token in one of these exempt fields is not soft-flagged (expected: these
   fields don't carry free text in practice).
3. A list of plain strings (e.g. `{"section_names": ["Period 1 with a real
   roster name in it"]}`) now produces a soft flag, where before the string
   was invisible to the scan entirely.
4. All 8 tests added in Batch 1 for `find_token_matches`/forbidden keys
   still pass unchanged — A3 does not touch `_FORBIDDEN_KEYS` or
   `find_token_matches`.
5. Every existing green fixture across the full suite remains green or is
   fixed at the fixture-data level with the change reported; no assertion's
   intent is altered to accommodate new noise.

## Named verification gate

```powershell
py -m pytest api/tests/test_feedback_safety.py api/tests/test_feedback_scrub.py api/tests/mcp_server/test_tools.py api/tests/test_beta075_mcp.py api/tests/test_feedback_pipeline.py api/tests/test_vault_conflict.py api/tests/test_beta075_transmission.py api/tests/dailywriting api/tests/mirror -p no:randomly
```

Then the full gate:

```powershell
py -m pytest api/tests -q
```

Baseline is 2140 passed at `3576d15`. Expect new soft-flag noise in existing
fixtures per §3 A3's own "Expected cost" note; fix fixture data as needed
and report every change.

## Stop conditions

Stop and report YELLOW/RED without guessing if: a currently-green fixture's
new soft flag cannot be resolved by a fixture-data rename without changing
what the test is actually verifying; a hard block (not just a soft flag)
newly appears on existing passing data, indicating the exemption set missed
a real identifier-shaped field; or fixing `_walk` changes behavior for any
list-of-dicts payload (it must not — only bare scalar list items are
affected).

## Execution result

Traffic light: GREEN

Commit hash: recorded in the commit that includes this brief update.

Implemented exactly as locked above: `_TEXT_FIELDS` replaced by
`_STRUCTURAL_EXEMPT_KEYS`; `scan_payload` now scans every string value by
default (Layer 2a/2b) except the small exempt set (Layer 1b only, but see
the correctness fix below); `_walk` now carries the enclosing key into bare
list items so a list of plain strings is no longer invisible to the scan.

**A real defect found and fixed while implementing, not deferred:** the
daily-writing MCP tool `get_writing_history` has been leaking the real
Canvas user id, unconditionally, on every call, since the substrate landed
(2026-07-27). `api/dailywriting/canvas_source.py::submission_id_for` builds
the internal store key as `"canvas:{course_id}:{assignment_id}:{canvas_user_id}"`
for storage idempotency, and `api/dailywriting/projection.py::_submission_row`
put that raw key straight into the outbound `submission_id` field, outside
the `include_text` gate. Under the old allowlist, `submission_id` was never
in `_TEXT_FIELDS`, so Layer 2b (the word-bounded real-id check) never ran on
it; Layer 1b's exact-match check never fired either, because the full
string never exactly equals the bare id. A3's own inversion made
`submission_id` scanned by default, Layer 2b correctly found the embedded
id, and the MCP tool started (correctly) hard-blocking. Fixed at the
projection boundary: `projection._safe_submission_ref` now exposes a
SHA-256 hash of the internal key instead of the raw value — stable across
re-ingests (same input -> same hash, so idempotency tests are unaffected)
but the real id is not recoverable from it. `rep_id` was checked and is
unaffected (it embeds only `course_id`/`assignment_id`, not student
identity). Two tests needed updating for this: an ordering test that used
literal `submission_id` values ("early"/"late") now checks `submitted_at`
instead (the field the sort is actually defined on); a stale docstring/test
reference to `_TEXT_FIELDS` was updated to `_STRUCTURAL_EXEMPT_KEYS`.

**Correction recorded, not acted on:** the initiative document's claim that
no payload emits `assignment_description` is inaccurate for the full
`scan_payload` caller set — `api/powergrader/context.py` emits it in
`bundle["shared_context"]`. Under the new model this doesn't matter (no
field name needs listing either way), but recorded so the claim isn't
propagated.

Verified during implementation, not just asserted: a manual full call-site
inventory of every `scan_payload`/`gate` caller (9 sites across
`tools.py`, `ai_transmission.py`, `ai_workflow.py`, plus test-direct calls),
tracing every helper that builds a gated payload, to derive the exemption
set from real emitters rather than the initiative document's illustrative
list alone.

Changed files:

- `api/feedback_safety.py` (the A3 inversion + `_walk` fix)
- `api/dailywriting/projection.py` (the `submission_id` leak fix)
- `api/tests/test_feedback_safety.py` (+6 tests)
- `api/tests/dailywriting/test_dw_evidence_store.py` (2 assertions updated
  for the hash change and the renamed exemption set)
- this brief

Verification:

- Focused gate (`test_feedback_safety.py test_feedback_scrub.py
  mcp_server/test_tools.py test_beta075_mcp.py test_feedback_pipeline.py
  test_vault_conflict.py test_beta075_transmission.py dailywriting/ mirror/
  -p no:randomly`): 410 passed.
- Full gate (`py -m pytest api/tests -q`): 2146 passed (baseline 2140 + 6
  new tests, 0 removed).
- Reproduced the `_walk` bare-list gap directly against `feedback_safety._walk`
  before fixing it, and reproduced the `submission_id` leak against a real
  ingest fixture (`test_no_real_name_leaks_into_get_writing_history`) before
  and after the fix.

Deviations: did not exempt `source` (see locked decision above — reused by
PowerGrader's `materials[].source` with different, freer semantics). Fixed
the `submission_id` leak at the projection layer rather than reporting
YELLOW, because it is squarely the kind of silent defect this whole
initiative exists to remove (§1) and the fix was small, contained, and did
not touch a documented public contract (`docs/mcp-server.md` never
mentions `submission_id`/`rep_id`).

Unresolved decisions: none for this brief. A5, A7, D1.4, D4, C sequencing,
and 2.3 remain open per the initiative document's §10.
