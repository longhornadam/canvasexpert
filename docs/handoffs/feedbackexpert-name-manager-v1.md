# Handoff: FeedbackExpert V1 — Name Manager + Scrub + SAFE/PRIVATE folders

> **STATUS: IMPLEMENTED (on `dev`).** This is a historical build spec, kept for context.
> All six tasks shipped, plus **Push to Canvas** (Phase C) and **plain-text code-file scoring**
> (the v1.1 "attachment-only excluded" deferral below was closed — `.py`/`.html`/etc. uploads
> are now scored). For current behavior see `CLAUDE.md` and
> `docs/contracts/feedback-scoring-contract.md`; don't treat the "OUT/deferred" items below as
> still-open without checking the code.

**Lane:** Ferrari-planned, Toyota-implementable. This doc is self-contained — do not
round-trip to the planner. Read it fully before starting.

**Context (why this exists):** FeedbackExpert lets a teacher hand student writing to *any*
LLM safely. The privacy model: real names never leave the machine; the teacher works from a
**SAFE** (pseudonymized) copy, takes it to ChatGPT/Claude/MagicSchool, and enters
grades/feedback by hand in Canvas SpeedGrader using a **who-is-who** decoder. There is **no**
automated re-identification or push-to-Canvas in this build (that's parked — see "Do not
touch"). The headline product is: *consistent pseudonymization the teacher can trust, plus a
screen to manage names.*

**Big idea that drives every task:** the consistent, authoritative identity is the **Canvas
API `user` object** (keyed by `canvas_id`) — never the name *inside* the student's writing,
which is inconsistent (kids sign "Jose", "Paco", "J.F.", or nothing). So we **anchor on the
API name** and **scrub the content aggressively**, matching every known form of every roster
name. We bias hard to **over-correction**: a false scrub is fine; a leaked real name is not.
Filenames are **free** — we generate them ourselves, so SAFE files are named with the
pseudonym from the start and never contain a real name to clean up.

---

## V1 scope (locked)

**IN:**
1. SAFE / PRIVATE / `_system` folder zones + `__SAFE` / `__PRIVATE` filename tags.
2. Vault schema v2: per-student `nicknames[]` + **realistic fake-name** pseudonyms (e.g.
   "Sparky McGee"), drawn from a pool disjoint from the real roster, stable per `canvas_id`.
3. Protected-names store (synced, **not** PII) + literary "character packs" (Outsiders,
   Hunger Games, Giver, Romeo & Juliet) the teacher toggles on, plus custom entries.
4. Scrub engine: roster-wide token map, protected-name allowlist, content-only,
   over-correcting, with a verify-receipt pass.
5. Safety gate flip: pipeline **scrubs then verifies** (no warn-and-stop, no quarantine).
6. **Name Manager** WebUI screen: roster sync, editable nickname + pseudonym table,
   protected-names editor w/ pack toggles, collision detection, live scrub-test box,
   who-is-who export.
7. SAFE pipeline emits pseudonym-named files; PRIVATE keeps the real-name copy + who-is-who.

**OUT (defer to v1.1 — name them in the UI so nothing "appears broken"):**
- **Attachment scrub** (docx/pdf extracted text **and** document-author metadata). V1 scores
  **text entries only** (`submission.body`); attachment-only submissions are listed but
  **excluded from SAFE** with a visible "not yet scrubbed" note.
- Bulk nickname CSV import (manual entry is fine for classroom-size rosters in v1).
- Automated re-identification / Phase C push (parked).
- Full vault-health analytics (v1 ships only: count, last-sync, one-click backup).

---

## Guardrails (non-negotiable — see CLAUDE.md)

- **FERPA:** real names / canvas_id / sis_id / nicknames are PII. They live **only** in the
  vault (`FeedbackExpert/_system/vault/`, synced-private) and the PRIVATE folder. Never the
  repo, a test fixture, a log, or a SAFE file. Protected (literary) names are **not** PII and
  may ship in-repo / sync freely.
- **Local-only:** Name Manager is a normal `127.0.0.1` WebUI screen. Do not add public routes.
- **No district/PII in repo:** the fake-name pools and literary packs are generic, shippable.
  No real roster, school, or teacher name anywhere in source.
- **Over-correct, never block:** the user is never shown a "you must fix this" dead-end. If a
  name can't be scrubbed safely, the safe default wins (scrub/over-scrub or exclude), and the
  situation is *surfaced*, not *blocking*.

## Do NOT touch

- `LLM_Modules/*_Base.md` authoring contracts.
- `docs/contracts/feedback-scoring-contract.md`, `feedback_pipeline.validate_results`,
  `feedback_pipeline.reidentify`, and the `3_FromLLM`/ToEnter push path — **parked, keep as
  dormant code.** Don't delete; don't extend. (A future auto-push may reuse them.)
- New Quizzes write-back (parked, PAT/403 limit).

## Tests / run

```powershell
py -m pytest api/tests          # all FeedbackExpert tests live here
cd api; py qf_ui.py             # http://127.0.0.1:8765  — Name Manager under the Feedback nav
```

---

# Tasks (ordered; each is independently shippable)

## Task 1 — Vault schema v2 + fake-name generator

**File:** `api/feedback_vault.py` (+ new `api/data/fake_first_names.txt`,
`api/data/fake_last_names.txt`; + `api/tests/test_feedback_vault.py`).

**Schema change.** Each `_by_id[canvas_id]` entry becomes:
```python
{"pseudonym": "Sparky McGee", "pseudo_first": "Sparky", "pseudo_last": "McGee",
 "real_name": "Jose Flores", "sis_id": "...", "nicknames": ["Paco"],
 "first_seen": "..."}
```
No migration needed (the vault has never been used in production). Old `S001` scheme is
**replaced**, not preserved.

**Fake-name generator.**
- Ship two name pools as plain-text, one name per line, ~200 each, generic/whimsical, **no
  real student names** (`api/data/fake_first_names.txt`, `fake_last_names.txt`).
- `get_or_assign(canvas_id, real_name="", sis_id="", roster_names=None)`: on first sight,
  assign a `first last` fake name where **neither token collides** with (a) any real roster
  name token in `roster_names` (pass the class's real first/last tokens), nor (b) any fake
  name already in the vault. Deterministic given the same inputs is **not** required; just
  stable once assigned (persisted).
- Keep `canvas_id` keying so a student keeps one identity across courses/years.

**New methods:**
```python
def set_nicknames(self, canvas_id, nicknames: list[str]): ...   # dedups, strips; auto-saves? no — caller saves
def set_pseudonym(self, canvas_id, first: str, last: str): ...  # manual override from the UI
def regenerate_pseudonym(self, canvas_id, roster_names=None): ...# new fake name, collision-checked
def entries(self) -> list[dict]: ...                            # [{canvas_id, real_name, sis_id, nicknames, pseudonym, pseudo_first, pseudo_last}] for the UI table
```
**`all_real_identifiers()` must now include nicknames** in the returned `names` set (so the
scanner/scrubber catches "Paco").

**Edge cases:** empty/blank real_name (keep canvas_id, pseudonym still assigned); duplicate
nicknames; a nickname equal to another student's real name (allowed — the scrub map handles
precedence later); pool exhaustion (if pools run dry, append a numeric suffix to a fake name).

**Tests:** stable pseudonym across calls; fake name never equals a roster token; nicknames
round-trip and appear in `all_real_identifiers()`; `entries()` shape; regenerate produces a
different, still-non-colliding name.

## Task 2 — Protected-names store + literary character packs

**File:** `api/webui/config.py` (mirror the persona/pattern synced-store pattern:
`_synced_state()` / `_save_synced_key()` / builtin-list + custom-additions).

**Shipped packs** (constant, like `BUILTIN_PERSONAS`):
```python
LITERARY_PACKS = [
  {"id": "outsiders",  "title": "The Outsiders",
   "names": ["Ponyboy","Johnny","Dally","Dallas","Sodapop","Darry","Two-Bit","Cherry","Bob"]},
  {"id": "hunger_games","title": "The Hunger Games",
   "names": ["Katniss","Peeta","Gale","Prim","Haymitch","Effie","Rue","Cinna","Snow"]},
  {"id": "giver",       "title": "The Giver",
   "names": ["Jonas","Asher","Fiona","Gabriel","Lily"]},
  {"id": "romeo_juliet","title": "Romeo & Juliet",
   "names": ["Romeo","Juliet","Tybalt","Mercutio","Benvolio","Capulet","Montague","Friar"]},
]
```
**API:**
```python
def list_protected_packs() -> list[dict]:   # packs + {enabled: bool} from synced state
def set_pack_enabled(pack_id: str, enabled: bool): ...
def get_custom_protected_names() -> list[str]: ...
def set_custom_protected_names(names: list[str]): ...
def active_protected_names() -> set[str]:   # union of enabled packs' names + custom, lowercased
```
Storage keys: `"protected_packs_enabled": {pack_id: bool}`, `"protected_names_custom": [...]`.
**Not PII** — fine to sync and to ship the packs in-repo.

**Tests:** toggling a pack changes `active_protected_names()`; custom names merge in; disabled
packs excluded.

## Task 3 — Scrub engine + safety-gate flip

**Files:** new `api/feedback_scrub.py`; edit `api/feedback_safety.py`; tests
`api/tests/test_feedback_scrub.py`.

**`feedback_scrub.py`:**
```python
def build_replacement_map(vault_entries: list[dict], protected: set[str]) -> list[tuple]:
    """Return [(compiled_regex, replacement)] for the WHOLE roster, sorted longest-token-first.
    Per student, map: full real name -> full fake name; first->pseudo_first; last->pseudo_last;
    each nickname -> pseudo_first. A token that is ALSO in `protected` is STILL scrubbed
    (roster identity wins over a literary match — privacy first). `protected` only shields
    words that are NOT roster tokens."""

def scrub_text(text: str, replacement_map) -> str:
    """Apply the map. Word-boundary, case-insensitive; possessives fall out naturally
    (\\bJose\\b matches in 'Jose's' -> 'Sparky's'). Longest patterns first so
    'Jose Flores'->'Sparky McGee' beats the single-token rules."""

def find_collisions(vault_entries, protected: set[str]) -> dict:
    """{ 'literary': [...real names that match a protected literary name...],
         'dup_first': [...first names shared by 2+ students...],
         'common_word': [...nickname/name tokens that are very short (<=2) or in COMMON_WORDS...] }
    For the UI to surface — none of these block anything."""

def verify_clean(text: str, vault) -> list[str]:
    """Re-scan scrubbed text for any surviving real identifier (vault.all_real_identifiers()
    names). Returns survivors. With over-correction this should be empty; a non-empty result
    is a BUG to log, never a user task."""
```
Ship a small `COMMON_WORDS` set (English stop-ish words + common name-words like
"will","rose","summer","may","grace") for the `common_word` collision hint.

**`feedback_safety.py` flip.** Keep `scan_payload` and its HARD layer as the structural
backstop (forbidden identity *keys*, raw ids as values — these mean a pipeline bug, not user
content). The **SOFT layer becomes a receipt, not a warning**: the pipeline now scrubs *before*
the payload is built, so SOFT findings should be empty. Add a thin helper the pipeline uses:
```python
def assert_scrubbed(payload, vault) -> dict:
    """scan_payload + return it; intended to run AFTER scrubbing. green must be True and soft
    should be []; a non-empty soft is logged as a scrub miss (bug), not surfaced to the user."""
```
Do not change the HARD semantics.

**Edge cases:** two students share a first name → both first-name tokens map (last-writer in
the regt is fine for privacy; decoder ambiguity is surfaced by `find_collisions`, not solved
here). A real name that equals a protected literary name (kid named "Romeo") → **scrubbed**
(roster wins), collision surfaced. Overlapping tokens ("Anne" vs "Anne-Marie") → longest-first
ordering handles it. Empty protected set is valid.

**Tests:** "Jose Flores", nickname "Paco" all → the same student's fake tokens in a sentence;
a cross-student mention ("I worked with Jose") is scrubbed; a protected literary name with no
roster collision is **preserved**; a roster name colliding with a protected name is
**scrubbed**; `verify_clean` returns [] on scrubbed output and the surviving token on
un-scrubbed input; possessive "Jose's" → "Sparky's".

## Task 4 — SAFE / PRIVATE / _system folder restructure

**Files:** `api/webui/workspace.py`; `api/webui/routes/pages.py` (the `feedback_expert_page`
folder map); `api/webui/routes/feedback.py` (every `feedback_folder("…")` call);
`api/feedback_pipeline.py` (`process_inbox` / `reidentify_dir` dir args — these are the parked
NQ/own-tool lane; just repoint their folder names, don't redesign them); update
`api/tests/test_feedback_pipeline.py` dir names.

**New `FEEDBACK_SUBFOLDERS`:**
```python
FEEDBACK_SUBFOLDERS = ["SAFE", "PRIVATE", "_system"]
# zone subpaths used by code:
#   SAFE/            -> pseudonymized work to score (+ HOW-TO-SCORE.txt)
#   PRIVATE/         -> raw downloads / NQ drops + who-is-who.csv
#   _system/vault/   -> the vault (was _vault/)
#   _system/archive/ -> processed originals (was _archive/)
#   _system/audit/   -> audit.log (was _audit/)
```
Add `feedback_folder` callers/constants for the new paths. Provide a **one-time migration**
in `ensure_workspace()`: if old `_vault/vault.json` exists and the new `_system/vault/` does
not, move it (and `_archive`,`_audit`). Folder zone names carry a human label via a seeded
`READ-ME (what's safe to share).txt` at the FeedbackExpert root — short, plain-English: "SAFE
= fake names only, paste anywhere. PRIVATE = real names, never leaves this PC. _system =
don't touch."

**Acceptance:** fresh `ensure_workspace()` creates the three zones; an existing old layout
migrates the vault without data loss; no code references the old numbered folders except the
parked NQ lane (which now points at SAFE/PRIVATE).

## Task 5 — Name Manager WebUI screen

**Files:** new `api/webui/templates/name_manager.html`; new route in
`api/webui/routes/pages.py` (`@router.get("/name-manager")`, `nav_section="feedback"` or a new
`"names"` nav item — add to the nav template alongside Feedback Expert); new JSON endpoints in
`api/webui/routes/feedback.py` (it already imports the vault + workspace).

**Endpoints:**
```
GET  /api/names/roster?course_id=...     -> sync roster (GET /api/v1/courses/{id}/users via
                                            _canvas_get_all), upsert into vault, return entries()
                                            joined with real name/section. Reuse the existing
                                            users fetch (see routes/courses.py / reports.py).
POST /api/names/nickname  {canvas_id, nicknames:[...]}      -> vault.set_nicknames + save
POST /api/names/pseudonym {canvas_id, first, last}          -> vault.set_pseudonym + save
POST /api/names/pseudonym/regenerate {canvas_id}            -> vault.regenerate_pseudonym + save
GET  /api/names/protected                                   -> list_protected_packs + custom
POST /api/names/protected {packs:{id:bool}, custom:[...]}   -> set_pack_enabled + set_custom...
GET  /api/names/collisions?course_id=...                    -> feedback_scrub.find_collisions
POST /api/names/scrub-test {text, course_id}                -> scrub_text using current roster+protected (live preview)
POST /api/names/who-is-who {course_id}                      -> write PRIVATE/<course>__who-is-who.csv, return path
```
All endpoints are local; they touch the vault (PII) which is fine (synced-private). **Never**
return SIS in the scrub-test or log it.

**Screen layout:**
- **Course picker** → "Sync roster" button.
- **Table:** Real name | Nickname(s) (editable, comma-sep) | Pseudonym (editable first/last +
  "🎲 regenerate") | Section. Inline save per row.
- **Collisions panel:** the three `find_collisions` buckets, each row a plain-English note
  ("Romeo is both a student and an Outsiders/​R&J character — his name will still be hidden").
  Informational only.
- **Protected names panel:** pack toggles (Outsiders / Hunger Games / Giver / R&J) + a custom
  textarea.
- **Scrub-test box:** textarea in, scrubbed text out, live — the trust-builder.
- **Footer:** vault count, last-sync time, "Back up vault" button (copies vault.json to
  `_system/vault/backups/vault-<date>.json`), "Export who-is-who" button.

**Acceptance:** sync a course → students appear with auto fake names; edit a nickname → persists
+ immediately changes scrub-test output; toggle a literary pack → a character name stops being
scrubbed in the test box; a student named after a character shows in collisions but is still
scrubbed; who-is-who export lands in PRIVATE with real↔fake rows.

## Task 6 — Wire the SAFE pipeline to scrub + pseudonym filenames

**Files:** `api/feedback_pipeline.py` (`pseudonymize_submissions`, `write_bundle`);
`api/webui/routes/feedback.py` (the guided `/run/prepare` path that calls them).

**Behavior:**
- After building per-student responses, **scrub every `response` (and `prompt` if it names
  students)** with `feedback_scrub.build_replacement_map(vault.entries(), config.active_protected_names())`.
- Run `feedback_safety.assert_scrubbed(bundle, vault)` — green required; log any soft miss.
- Write the SAFE bundle to `SAFE/`, named with the **assignment title only** (never a student
  name). Per-student readable `.txt` files (if emitted) are named with the **pseudonym**
  (`Sparky-McGee__SAFE.txt`), never the real name.
- Write the raw identified pull to `PRIVATE/<assignment>__PRIVATE.json` and the
  `who-is-who.csv` for that batch.
- **Attachment-only submissions** (no `body`, has `attachments`): **exclude from SAFE**, list
  them in the run summary as "N submissions are file uploads — not scrubbed in v1, score these
  manually." (Do not emit unscrubbed attachment text.)

**Acceptance:** run the guided prepare on a text-entry assignment → SAFE bundle has fake names
only, `verify_clean` passes, PRIVATE has the real-name copy + decoder; an attachment-only
submission is reported as skipped, not leaked.

**Tests:** extend `api/tests/test_feedback_pipeline.py` — `pseudonymize_submissions` output
contains no roster token (assert via `verify_clean`); attachment-only entry is excluded;
filenames carry pseudonym/assignment, never real name.

---

## Suggested order

1 → 2 → 3 (pure, fully unit-testable foundation) → 4 (folders) → 6 (pipeline wiring) → 5 (UI
on top). Tasks 1–3 and 4 can proceed in parallel; 5 and 6 depend on 1–3.
