# SmartDeck slice 2 — DeckForge contract, validation, and the MCP write surface

**Lane:** Toyota implementation, **Ferrari review required before merge.** This slice adds the
first tool that lets an AI write to the teacher's synced workspace. The logic is
straightforward; the blast radius is not.
**Depends on:** slice 1 (`deck_schedule.resolve_day`, `deps.load_teacher_schedule`).
**Blocks:** slices 3 and 4.
**Design spine:** `docs/reference/smartdeck-design.md` §2, §3.3, §3.4, §5, §7, §8.

## Goal

An AI can author a SmartDeck for a date and save it. A saved deck is a validated JSON file in
`<workspace>/SmartDecks/Decks/`. Nothing reaches the projector until the teacher clicks
Display (slice 3) — **that click is the only human gate, by design**, so the write path itself
must be narrow and unable to escape its folder.

## The write-surface decision (read this before coding)

The MCP server is read-only today: five tools, all fetches. The docstrings at the top of both
`api/mcp_server/tools.py` ("the 5 read-only MCP tools") and `api/mcp_server/server.py`
("Five thin `@mcp.tool()` wrappers") say so. **Both docstrings must be updated in this slice** —
leaving them is how a future reader concludes writes are impossible.

Three rules, non-negotiable:

1. **Path jail.** Every resolved path passes `workspace.path_within_workspace()`
   (`api/webui/workspace.py:529` — realpath + commonpath) *and* must sit under
   `<workspace>/SmartDecks/`. Reject otherwise. The `date` argument reaches the filesystem, so
   it is attacker-shaped input: validate against `^\d{4}-\d{2}-\d{2}$` **and** run the result
   through `workspace.safe_component()`.
2. **Never overwrite.** Each save writes a new revision. No code path in this slice may
   `open(path, "w")` over an existing deck.
3. **Atomic writes.** Copy `workspace.write_assignment_evidence_manifest()`
   (`api/webui/workspace.py:326`) exactly: `tempfile.mkstemp` in the target dir →
   `json.dump(..., indent=2, sort_keys=True)` → `flush()` → `os.fsync()` → `os.replace()` →
   `unlink` the temp file in `finally`. A half-written deck must be impossible.

## Files to change

### NEW `LLM_Modules/DeckForge_Base.md`

The canonical contract. Write it with the rigor of `QuizForge_Base.md` — read
`PageForge_Base.md` first for the shortest example of the house structure. It is **canonical**:
once written, `api/` consumes it and never "fixes" it by editing backend code (CLAUDE.md).

Envelope `<DECKFORGE_JSON> … </DECKFORGE_JSON>`, `version: "1.0-json"`, `type: "DECK"`.

```
{ "version": "1.0-json",
  "type": "DECK",
  "date": "2026-08-14",
  "title": "Thursday - Ch. 3 quiz day",
  "widgets": [ { "id": "w1", "scope": "deck", "kind": "timer",
                 "params": {"duration_seconds": 300, "label": "Bell work", "autostart": true} } ],
  "slides": [ { "id": "s1", "block": "4th/5th", "layout": "title_body",
                "title": "...", "body": "...", "widgets": ["w1"] } ] }
```

Fix in the contract: the `layout` vocabulary for v1 (keep it small — `title_body`,
`title_only`, `bulleted` is enough), `widget.kind` = `"timer"` only, `scope` ∈
`{deck, slide}`, and `block` = a Teacher Schedule block **name** (never a clock time, never a
raw period number — §2.1).

**Reserve `slide.feed` in the schema and document it as not-yet-supported.** Slice 2 rejects
it. That keeps slice 5's feed work from being a breaking contract change.

### NEW `api/webui/df.py`

Structural twin of `api/webui/pf.py` — read that file (49 lines) and follow it literally.

```python
ENVELOPE_RE = re.compile(r"<DECKFORGE_JSON>\s*(\{.*\})\s*</DECKFORGE_JSON>", re.S)

def parse_file(path): ...        # -> (data|None, problems)
def parse(text): ...             # -> (data|None, problems)
def validate(d): ...             # -> problems (list[str])
```

Pure. No HTTP, no file IO beyond `parse_file`, no `workspace` import, **no Canvas Mirror
access**. `validate()` is the piece the MCP tool calls directly on an already-parsed dict —
the write path never needs the envelope, but `parse`/`parse_file` exist so a paste-box UI or a
file-based test costs nothing later.

`validate()` checks, each with its own message:

- `version == "1.0-json"`, `type == "DECK"`, `date` matches `^\d{4}-\d{2}-\d{2}$`
- non-empty `slides`; every slide has a unique non-empty `id`
- every `slide.block` is a non-empty string (**existence is *not* checked here** — that needs
  the teacher schedule, which is IO; the caller cross-checks. Say so in the docstring.)
- every `widget.id` unique; every `slide.widgets[]` entry references a declared widget id
- `widget.scope` ∈ `{deck, slide}`; `widget.kind == "timer"`; unknown kind → problem naming
  the allowed set
- timer `params.duration_seconds` is an int in `1..86400`
- **a `feed` key anywhere → `"feed bindings are not supported in v1"`** (the reserved-field
  rejection above)
- **unknown top-level keys → a problem.** Closed schema, not open. This is the same
  allowlist reflex as §5.2's feed catalog: things are permitted because they're listed, not
  because nothing forbade them.

### NEW `api/webui/deck_store.py`

The only module in the codebase that writes deck files. Imports `workspace`, `df`.

```python
DECKS = "Decks"; ARCHIVED = "Decks/Archived"

def _decks_dir(): ...                          # <workspace>/SmartDecks/Decks  (jailed)
def next_revision(date) -> int: ...            # scans <date>.r*.json, returns max+1
def save_deck(data) -> tuple[dict|None, list[str]]:
    """Validate -> jail-check -> archive prior revisions of this date -> atomic write.
    Returns ({deck_id, path, revision}, problems). problems non-empty => nothing written."""
def list_decks(status="active") -> list[dict]:  # status in {active, archived}
def load_deck(deck_id) -> tuple[dict|None, list[str]]
def archive_deck(deck_id) -> tuple[bool, list[str]]
def delete_deck(deck_id) -> tuple[bool, list[str]]
```

Naming: `deck_id` == the filename stem, `2026-08-14.r3`. Sortable, human-legible in OneDrive,
and revision-explicit.

**§3.4 falls out of this for free:** `save_deck` archives every existing revision for that date
before writing the new one, so "mid-day re-author archives what it replaces" is one code path,
not a special case.

**Delete is non-destructive.** `delete_deck` *moves* the file to
`<workspace>/_System/Archive/SmartDecks/` (that `Archive` system folder already exists —
`workspace.SYSTEM_SUBFOLDERS`). It never calls `os.unlink`. This is a deliberate deviation
from a literal reading of the design doc's "Delete" action: `workspace.py`'s whole ethos is
non-destructive ("does not automatically rename, move, overwrite, or delete"), and a deck is
teacher-authored work in a synced folder. The UI may still label the button *Delete*.

### EDIT `api/mcp_server/tools.py`

Four write tools + one read, house style (`{"ok": ...}`, never raise):

```python
def save_deck(date: str, title: str, slides: list, widgets: list = None) -> dict
def list_active_decks() -> dict
def archive_deck(deck_id: str) -> dict
def save_teacher_schedule(blocks: list) -> dict
def save_day_calendar(year_label: str, entries: list) -> dict
```

`save_deck` assembles the contract dict, calls `df.validate()`, and on any problem returns
`{"ok": False, "problems": [...]}` **without writing**. On success it also cross-checks each
`slide.block` against `deps.load_teacher_schedule()` and returns unknown block names as
problems — the check `df.validate()` deliberately can't do.

`save_bell_schedule` is **not** included: bell schedules are school-wide public data that
ships as seed CSV (slice 1) and changes once a year by hand. An AI write tool for it is
surface with no use case.

These tools take no `course_id` and touch no student data, so — like `list_courses` — they
skip the course gate and the outbound safety gate. Comment that this is intentional.

### EDIT `api/mcp_server/server.py`

`@mcp.tool()` wrappers + fix the "Five thin wrappers" docstring.

### NEW tests

- `api/tests/test_df.py` — validation table, one case per rule above.
- `api/tests/test_deck_store.py` — **including the jail tests**, modeled on
  `api/tests/test_canvas_mutation_ownership.py`'s guardrail style:
  - `date` of `"../../../evil"`, `"2026-08-14/../.."`, an absolute path, a UNC path → refused,
    nothing written anywhere.
  - Two saves for one date → `r1` archived, `r2` active, `r1` still readable.
  - `save_deck` with a validation problem → **zero files created** (assert the dir is empty).
  - Simulated failure mid-write (monkeypatch `os.replace` to raise) → no partial file left.
  - `delete_deck` → file present in `_System/Archive/SmartDecks/`, absent from `Decks/`.
- EDIT `api/tests/test_mcp_server_tools.py` — add the new tools, monkeypatching the workspace
  root to a tmp dir (follow the existing monkeypatch seams noted in that file's header).

## Test command

```bash
py -m pytest api/tests/test_df.py api/tests/test_deck_store.py api/tests/test_mcp_server_tools.py -v
```

## Acceptance criteria

- No path outside `<workspace>/SmartDecks/` is writable through any tool in this slice, proven
  by the jail tests above.
- A failed validation writes nothing — asserted, not assumed.
- Saving twice for one date leaves exactly one active revision and the prior one archived.
- `grep -rn "open(" api/webui/deck_store.py` shows no `"w"` mode against a deck path; all
  writes go through the mkstemp/fsync/replace helper.
- Both MCP docstrings no longer claim the server is read-only.
- `LLM_Modules/DeckForge_Base.md` exists and documents `feed` as reserved-and-rejected.
- `py -m pytest api/tests` is green.

## Guardrails

- **#2 (FERPA):** this slice must not read a roster, gradebook, or Canvas Mirror. A deck
  contains authored text and feed *names* only. If a student name can reach a deck file in
  this slice, the design has been violated — stop and escalate to the Ferrari lane.
- **#4 (local-only):** no new network calls, no new bind address, no new served route.
- **Contract rule:** once `DeckForge_Base.md` exists it is canonical. If `df.py` and the
  contract disagree, fix `df.py` — or amend the contract deliberately, in the contract file.

## Do not touch

- The five existing MCP read tools' behavior.
- `api/webui/af.py`, `pf.py`, `rf.py` — read `pf.py` as the pattern; modify none of them.
- `api/operation_ledger/` — that subsystem is for Canvas mutations with receipts and recovery.
  Deck writes are local file writes. Emit an `operational_log` event (machine codes and
  counts only — `api/operational_log.py` forbids workflow data in that file) and nothing more.
- Feed resolution and Canvas Mirror. Not this slice, not slice 3, not slice 4.
