# SmartDeck slice 1 — schedule data + resolver

**Lane:** Toyota. Pure logic, no PII, no network, no write surface.
**Depends on:** nothing. This is the first slice.
**Blocks:** slices 2, 3, 4 all consume `resolve_day()`.
**Design spine:** `docs/reference/smartdeck-design.md` §2, §2.1, §3.1.

## Goal

Given a date, answer: *what instructional blocks does this teacher have today, and when
does each start and end?* Authored Slides bind to block **names**, never clock times, so a
Slide authored once keeps working on an early-release or assembly day (§2.1). That promise is
the acceptance test for this slice.

Three inputs:

| File | Format | Location | Who writes it |
|---|---|---|---|
| Bell Schedule (one per variant) | CSV | workspace `Calendars/` | ships as seed data; teacher may edit |
| Day Calendar (`date → schedule_id`) | CSV | workspace `Calendars/` | ships as seed data; AI regenerates per year (slice 2) |
| Teacher Schedule | JSON | workspace `SmartDecks/` | teacher or AI (slice 2) |

## Files to change

### NEW `api/webui/deck_schedule.py`

Pure stdlib. **No FastAPI, no `workspace` import, no file IO** — mirrors the contract at the
top of `api/webui/calendar_csv.py`. Callers pass text in; this module returns data out.

```python
def parse_bell_schedule(content: str) -> tuple[list[dict], list[str]]:
    """CSV text -> ([{period_id, start, end}], problems).

    Columns: period_id,start,end   (header row required)
    start/end are 24h "HH:MM" local wall-clock strings. No timezone math anywhere
    in this module -- a bell rings at 8:15 local regardless of DST.
    """

def parse_day_calendar(content: str) -> tuple[dict, list[str]]:
    """CSV text -> ({"YYYY-MM-DD": schedule_id}, problems).

    Columns: date,schedule_id   (header row required)
    Accepts YYYY-MM-DD or MM/DD/YYYY on input; keys are always YYYY-MM-DD.
    Match calendar_csv._pd()'s two-format tolerance -- teachers paste both.
    """

def parse_teacher_schedule(text: str) -> tuple[dict, list[str]]:
    """JSON text -> (data, problems). Shape:

    {"version": "1.0-json",
     "blocks": [{"name": "4th/5th", "raw_periods": [4, 5], "label": "ELA 7"}, ...]}

    raw_periods is ordered and may span more than one bell period (a combined
    block with no bell between them). label is optional display text.
    """

def resolve_day(date, day_calendar, bell_schedules, teacher_schedule) -> tuple[list[dict], list[str]]:
    """-> ([{name, label, start, end, raw_periods, schedule_id}], problems)

    date:            "YYYY-MM-DD"
    day_calendar:    output of parse_day_calendar
    bell_schedules:  {schedule_id: output of parse_bell_schedule}
    teacher_schedule: output of parse_teacher_schedule

    For each teacher block: start = start of its FIRST raw period, end = end of
    its LAST raw period, both taken from today's active bell schedule. Blocks are
    returned sorted by start. A block whose raw periods are absent from today's
    schedule is omitted from the list and reported in problems -- never guessed at.
    """
```

`problems` is a list of human-readable strings throughout, exactly like
`pf.validate()` — callers decide whether to warn or refuse. **No function in this module
raises on bad input.**

### EDIT `api/webui/deps.py`

Add the IO layer next to the existing `list_calendar_files()` (~line 43), following its lazy
`from . import workspace as _ws` pattern so the module stays importable pre-setup:

```python
def _smartdecks_dir():          # <workspace>/SmartDecks
def list_bell_schedule_files()  # -> [{name, label, schedule_id, path}]
def load_bell_schedules()       # -> ({schedule_id: periods}, problems)
def load_day_calendar()         # -> (mapping, problems)
def load_teacher_schedule()     # -> (data, problems)
def resolve_schedule_for(date)  # -> (blocks, problems)  -- loads all three, calls resolve_day
```

`schedule_id` is derived from the filename by the same slug rule
`routes/calendar.py::_calendar_key()` uses (`"Bell Schedule - Early Release.csv"` →
`bell_schedule_early_release`). **Reuse that function — do not write a second slug rule.**
Bell-schedule CSVs are discovered by the `Bell Schedule*` filename prefix so they don't
collide with academic-calendar CSVs in the same folder.

Every loader returns `(data, problems)` and returns `([], [reason])` — never raises — when the
workspace is unset or a file is missing. Slice 3 renders those reasons as the empty state.

### EDIT `api/webui/workspace.py`

Add `"SmartDecks"` to `WORKSPACE_SUBFOLDERS` (line 29). That single edit makes
`ensure_workspace()` both create `<workspace>/SmartDecks/` and seed it from
`api/default_docs/SmartDecks/` via the existing `_seed_folder_if_missing()` call at line 433.
**No new seeding code.**

### NEW seed data

- `api/default_docs/SmartDecks/Teacher Schedule.template.json` — a placeholder with two
  example blocks (one single-period, one combined) and no real course names.
- `api/default_docs/Calendars/Bell Schedule - Regular.csv` and one variant
  (e.g. `Bell Schedule - Early Release.csv`) — the school's **real** bell times.
- `api/default_docs/Calendars/Day Calendar <year>.csv` — the district's **real** day mapping.

The bell schedules and day calendar are covered by the **guardrail #3 carve-out** (CLAUDE.md,
added 2026-07-30): public, non-PII schedule data, intentionally shipped, do not "fix" it.
The **Teacher Schedule ships as a template only** — a filled-in one is per-teacher config,
which the carve-out does *not* cover. The real one is created in the workspace, never in
the repo.

### EDIT `api/mcp_server/tools.py` + `api/mcp_server/server.py`

Three **read** tools. Follow the existing house style exactly: plain function in `tools.py`
returning `{"ok": ...}` and never raising, thin `@mcp.tool()` wrapper in `server.py` calling
`_compact()`.

```python
def get_bell_schedule(schedule_id: str = "") -> dict   # "" -> all variants
def get_day_schedule(date: str) -> dict                # resolved blocks for one date
def get_teacher_schedule() -> dict
```

No `course_id`, no student data — so like `list_courses`, these skip both the
`config.active_courses()` course gate and the outbound safety gate. Say so in a comment.

### NEW `api/tests/test_deck_schedule.py`

## Edge cases (each needs a test)

1. Date absent from the Day Calendar → `([], ["no schedule for 2026-08-14"])`, not a crash.
2. Day Calendar names a `schedule_id` with no matching CSV → reported in `problems`.
3. A teacher block's `raw_periods` aren't in today's schedule (assembly day drops period 7) →
   block omitted, reason in `problems`, **other blocks still resolve**.
4. Combined block `[4, 5]` → start from period 4, end from period 5, one entry not two.
5. Combined block whose raw periods are non-adjacent in time → resolve anyway (first start,
   last end) and add a `problems` note; do not reorder or reject.
6. Duplicate `period_id` rows in one CSV → `problems`, last value wins deterministically.
7. `end` earlier than `start` on a row → `problems`, row kept as-is (don't silently swap).
8. Malformed JSON in Teacher Schedule → `({}, ["invalid JSON: ..."])`.
9. Empty CSV / header-only CSV → empty data, empty-ish problems, no crash.
10. `MM/DD/YYYY` dates in the Day Calendar normalize to `YYYY-MM-DD` keys.

## Test command

```bash
py -m pytest api/tests/test_deck_schedule.py -v
```

Then confirm nothing regressed:

```bash
py -m pytest api/tests
```

## Acceptance criteria

- **The §2.1 promise holds:** one authored Teacher Schedule, two Bell Schedule variants. The
  same block name (`"4th/5th"`) resolves to different clock times on a Regular day vs. an
  Early Release day, with **no change to the teacher schedule file**. This is the test that
  matters; write it first.
- Every loader degrades to `(empty, [reason])` when the workspace or a file is missing.
- `deck_schedule.py` imports only stdlib. `grep -n "^from\|^import" api/webui/deck_schedule.py`
  shows no `fastapi`, no `.workspace`, no `api.` imports.
- `py -m pytest api/tests` is green.
- MCP tools return `{"ok": ...}` dicts and never raise, even with a missing workspace.

## Guardrails

- **#3 (district data):** the carve-out permits the bell/day CSVs as seed files *only*. Do not
  hardcode any district value in `.py`. Do not add a code path that branches on a district,
  school, or teacher name. Do not ship a filled-in Teacher Schedule.
- **#2 (FERPA):** nothing in this slice touches a roster, a grade, or a student. If you find
  yourself importing `roster_service` or `gradebook_*`, stop — you're outside the slice.
- **#4 (local-only):** no network calls in this slice at all.

## Do not touch

- `LLM_Modules/*` — no contract work in this slice.
- `api/webui/calendar_csv.py` — read it for the format-tolerance pattern; do not modify it.
  Academic-calendar parsing stays its job. Cross-validating the Day Calendar against holiday
  rows is deliberately **deferred to a later slice**.
- `api/mcp_server/tools.py`'s existing five functions.
- Anything under `api/operation_ledger/`.
