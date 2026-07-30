# SmartDeck / DeckForge architecture design

**Origin:** `ce-scenes.txt` (initial teacher draft, working title "Scenes," formerly "Glass"),
refined through a naming/architecture Q&A on 2026-07-30.

**Status:** Design locked and **planned**. No code exists yet. Ferrari-lane review happened on
2026-07-30: the design was checked against the real code, eight open questions were decided
(§9.1), the guardrail carve-out was landed in CLAUDE.md, and the work was cut into four slice
files (§9.2). This document is the spine — read it for *why*; read the slice files for *what to
build*. Slice 2 still wants a Ferrari review before merge, because it introduces the first MCP
tool that can write to the teacher's workspace.

**Supersedes:** `ce-scenes.txt` — a teacher's thinking document, not a spec, and not checked
into this repo. It's worth reading for feature *intent* if you have it, but this document is
self-contained and authoritative: its naming, its mechanics, and its privacy model all
supersede that file. Nothing in `ce-scenes.txt` should be implemented as written on the
strength of appearing there.

---

## 1. Terminology

`ce-scenes.txt` used "Scenes" for both the whole feature and an individual authored screen,
and "pane" interchangeably with "Scene" for an individual screen. That collision is exactly
what prompted this rename.

| Old term (`ce-scenes.txt`) | New term | Meaning |
|---|---|---|
| "Scenes" (the tab/feature) | **SmartDeck** | The whole feature area, and also the authored unit a teacher Displays/Archives/Deletes — analogous to a PowerPoint *file*. |
| "Scene" / "pane" (an instance) | **Slide** | One screen inside a SmartDeck — analogous to a PowerPoint *slide*. A SmartDeck contains one or more Slides. |
| (unnamed) | **Widget** | An interactive component (timer, picker, text box, audio box) placed on a Slide or pinned to the whole SmartDeck. |
| "Scenes Base" template idea | **Deck Template** | A full starter SmartDeck (multiple pre-arranged Slides) a teacher/AI can start from. |
| (unnamed) | **Slide Template** | A single reusable Slide type/layout that can be dropped into any deck. |
| "the AI authors the scene(s)" | **DeckForge** | The MCP authoring contract for this feature, following the existing `QuizForge` / `AssignmentForge` / `PageForge` / `RubricForge` naming convention. Lives at `LLM_Modules/DeckForge_Base.md` once written. |
| "CanvasMirror" (PII section) | **Canvas Mirror** | Not a new component — this is the existing local mirror at workspace `_System/Canvas Mirror` (see `docs/reference/canvasmirror-1.0beta-information-spine.md`). DeckForge reads from it; it does not need its own PII store. |

---

## 2. Core concepts and data model

**SmartDeck** — the authored, listed, Displayed/Archived/Deleted unit. One SmartDeck covers
one school day. Contains one or more Slides, and may have deck-level Widgets pinned to it.

**Slide** — one screen within a SmartDeck. Has a layout, static content, optional dynamic
content (feed bindings — see §5), optional slide-level Widgets, and a **period binding** that
determines when it's shown (see §3.1). A slide-level Widget only appears while that Slide is
current; a deck-level Widget persists and keeps running (e.g. a countdown) across every Slide
as the deck advances.

**Widget** — an interactive component. Scope is either `deck` (pinned to the whole SmartDeck,
persists through Slide changes) or `slide` (tied to one Slide, disappears when that Slide
isn't showing). v1 ships a small set of solid built-ins — timer is the priority — with
parameters (duration, label, etc.) as the "authoring" surface. **v1 ships the timer and nothing
else** (§9.1 decision 4) — a student picker is explicitly excluded because it needs roster data
and would breach the feed-free boundary. Teachers/AI may be given the freedom to author
genuinely new widget types later; that extensibility mechanism is **not yet designed**
(open item, §9.4).

**Deck Template / Slide Template** — both live under one "Templates" tab section, listed
separately (Deck Templates: full starter decks like the reborn "Scenes Base"; Slide
Templates: individual reusable slide layouts).

**Bell Schedule** — school-wide, named schedule variants (e.g. "Regular," "Early Release,"
"Assembly"), each defining raw period IDs and their start/end times.

**Day Calendar** — a lightweight day-by-day file: `date -> schedule_id`, referencing a Bell
Schedule variant per school day. AI-bulk-generates this (a whole semester in one pass rather
than a teacher typing ~180 rows), and it's validated against the existing holiday/term
calendar (`Calendars/*.csv`) so a day can't silently have a schedule while also being marked
a holiday, or vice versa.

**Teacher Schedule** — a per-teacher file mapping the teacher's actual instructional blocks
to the school's raw bell-schedule periods, including combined blocks (e.g. this teacher's
"4th/5th" is one instructional block spanning raw Periods 4 and 5 with no bell in between).
Slides bind to Teacher Schedule block names, not raw school periods, so the same authored
Slide still shows during "4th/5th" regardless of which Bell Schedule variant is active that
day.

**Feed** — a named, schema'd reference to Canvas Mirror–backed data (e.g. `birthdays_today`,
`missing_assignments`, `staar_masters`, `positive_achievements`). The AI only ever binds a
Slide/Widget to a feed *name*; it never receives real (or pseudonymized) student-level values.
See §5 for the full privacy model.

### 2.1 Why period binding, not literal times

A Slide is authored once but must keep working when the school's bell times shift (early
release, assembly day). Binding a Slide to a period *name* (resolved through Teacher Schedule
→ Bell Schedule at render time) rather than a literal clock time means schedule changes never
require re-authoring existing Slides.

---

## 3. Runtime behavior

### 3.1 Auto-advance is client-side

The fullscreen Display view holds the day's SmartDeck and watches the clock locally. For each
Slide, it resolves the Slide's period binding through the Teacher Schedule and today's active
Bell Schedule (via the Day Calendar) to get an actual start/end time, and swaps Slides
automatically at those boundaries. No server round-trip is needed for routine transitions —
this keeps the projector view working even if the local backend is briefly unavailable.

### 3.2 Dynamic content is a snapshot, not a live feed

Content driven by a Feed (marquees, counts) is resolved once — at author time or on an
explicit refresh — and then stays static on screen. There is no background polling while a
deck is displayed. This keeps the privacy story simple (§5) and avoids surprising a
projected screen with data that changes mid-lesson.

### 3.3 One SmartDeck per day, created on request only

A SmartDeck's scope is exactly one school day. Nothing is generated automatically overnight
or by a background job in v1 — a deck for a given day exists only after the teacher asks the
AI to build it (that morning, the night before, or however far ahead they like).

### 3.4 Mid-day edits create a new deck

When a teacher asks the AI for a change mid-day (the `ce-scenes.txt` "offers a new Scene"
flow), the AI authors a **new** SmartDeck for that same date rather than patching the one
already projected. Creating the new deck automatically archives the one it replaces. The
teacher then manually clicks Display on the new deck to swap what's on the projector — there
is no push/live-reload of an already-projected screen.

### 3.5 Active list does not auto-archive by date

Past-day decks stay in the Active list until the teacher (or AI, on request) manually
archives or deletes them — there is no automatic end-of-day sweep in v1. This keeps the
mechanism simple at the cost of some manual tidying.

---

## 4. UI structure

New "SmartDeck" tab in the existing local Web UI (`api/webui/`, still bound to `127.0.0.1`
only — nothing about this feature changes CLAUDE.md guardrail #4). Layout is a left column
(1/4 width) that travels alongside a right column (3/4 width), per the original sketch. Right
column sections:

- **Active** — SmartDecks with Display / Archive / Delete actions each.
- **Templates** — two lists: Deck Templates and Slide Templates.
- **Archived** — archived SmartDecks.
- **Widgets** — the widget library (built-ins, plus any teacher-authored ones once that
  extensibility exists).

"Display" fullscreens a SmartDeck for projection. That fullscreen view keeps a persistent
toolbar/corner-icon chrome (Maximize/Minimize/Close, widget interactions) around whichever
Slide is currently showing, and deliberately **does not extend `base.html`** — a projected
screen must not carry app nav or a settings link. Slice 4 fixes the chrome's behavior
(persistent, reachable, ≥44px touch targets); the exact icon set remains a design call
(open item, §9.4).

---

## 5. Privacy / PII execution model

This is the part of the design most worth a second pair of eyes before implementation,
because it's where the AI-authorship boundary meets real student data.

### 5.1 The AI never sees a student-level value, real or fake

Unlike FeedbackExpert — where the LLM reads a specific student's pseudonymized submission and
writes a response to *that submission* — DeckForge's AI never operates on an individual
student at all. All classroom-facing display content for this feature is **purely
mechanical**: a Feed just renders as a plain list or marquee (name + assignment, name +
birthday) with zero AI-generated text per entry. Because of that, DeckForge needs no
pseudonymization or vault/re-identification step of its own. The AI's entire authored output
— Slide layout, Widget placement, Feed *bindings* — contains no student data whatsoever, so
it's safe to store, log, or inspect without any scrubbing pass.

### 5.2 The feed catalog is a closed allowlist

The mechanism is a **closed allowlist, not a blocklist**. There is exactly one hardcoded
catalog of feed names in the codebase; a feed exists if and only if it is in that catalog.
`df.py` validation rejects any feed name it doesn't recognize, so anything not deliberately
added is unreachable by construction — no enumeration of forbidden fields is needed, and none
should be written into the schema.

Feeds appropriate for a projector are things a class already sees out loud: names,
birthdays, missing-work lists, positive recognitions, schedules and events. Data that is
plainly not for a projector — discipline records, SpEd/504 status, contact and demographic
info, individual failing grades — simply never gets a catalog entry. That data is not absent
from Canvas Expert (Gradebook Expert and FeedbackExpert legitimately use it); it's just not
addressable from here.

Which specific feeds ship in v1 is an authoring decision made when the catalog is written,
and it should be reviewed once with a human before the catalog lands. The classroom-facing
vs. teacher-facing lists in `ce-scenes.txt` are **useful intent, not a normative
classification** — that file was a thinking document. Do not treat its categories or its
numeric cutoffs as a spec, and do not implement a threshold rule from it.

### 5.3 Resolution happens locally, at Display time, never through the AI

A DeckForge-authored Slide only ever contains a Feed *name* (e.g. `feed: birthdays_today`).
When that Slide actually renders on the projector, the local `api/` backend — which already
reads the existing Canvas Mirror (`_System/Canvas Mirror` in the workspace, see
`docs/reference/canvasmirror-1.0beta-information-spine.md`) — resolves the Feed reference
into real names/content and substitutes it into the rendered page. That substitution is
entirely local and never crosses back to the AI/MCP boundary.

### 5.4 Optional: aggregate stats without identity

If a future widget needs to make a layout decision based on volume (e.g. "will 12 birthdays
overflow this marquee vs. 1?"), an MCP tool like `get_feed_stats(feed_name, date)` could
return a count only — never names — so the AI can reason about scale without ever seeing who.
This is a nice-to-have, not required for v1.

---

## 6. District data guardrail carve-out

SmartDeck ships the school's real bell schedule and the district's real academic calendar as
in-repo defaults. Academic calendars and bell schedules are **public, non-PII information**
with no FERPA exposure, so this is settled policy, not an open question.

**CLAUDE.md guardrail #3 has been amended to say so** (carve-out added 2026-07-30). A future
agent reading CLAUDE.md will find the exception stated in writing and should not "fix" real
district schedule data it finds in `api/default_docs/`.

**Conditions the carve-out imposes** (these are the part an implementer must honor):

- The data ships as a **seed file** under `api/default_docs/` — for calendars, another CSV in
  `api/default_docs/Calendars/` next to the existing `calendar_template.csv` and
  `Summer_Session_Sample.csv`, seeded to the workspace `Calendars` folder like the others.
- **No district value gets hardcoded in `.py`**, and no code path special-cases a district.
  The existing loader (`api/webui/deps.py` → `_calendars_dir()`, and
  `api/webui/routes/calendar.py`) stays fully data-driven: it lists whatever is in the
  workspace folder. Bell schedules follow the same rule.
- The files carry **no student data and no per-teacher contact info**.

Everything else in guardrail #3 stands — this does not reopen Canvas URLs, rosters, or
teacher-identifying config.

---

## 7. Code structure

Following the existing repo conventions surveyed directly in `api/`:

**MCP tools** — new functions added to the existing `api/mcp_server/tools.py`, registered via
`@mcp.tool()` in the existing `api/mcp_server/server.py` (the single `canvas-expert` FastMCP
server, same install as today's `get_roster`/`get_gradebook_snapshot`/etc.). Likely additions:
`list_deck_templates`, `list_slide_templates`, `get_bell_schedule`, `get_teacher_schedule`,
`get_day_schedule(date)`, `list_widget_types`, `list_feeds`, `get_feed_stats(feed_name, date)`
(§5.4), `save_deck(date, slides, widgets)`, `list_active_decks`, `archive_deck(id)`. Exact
signatures belong in the DeckForge contract, not this doc.

**Parse/validate** — a new pure module **`api/webui/df.py`** (the `af.py` / `pf.py` / `rf.py`
siblings live in `api/webui/`, not `api/`): an envelope regex for a `<DECKFORGE_JSON>` tag,
`parse()` / `parse_file()`, and `validate()` — checking version/type/required fields, closing
the schema against unknown keys, and rejecting any Feed reference outside the allowed catalog
(§5.2). No HTTP, no Canvas Mirror access here — pure validation only. Because authoring goes
through an MCP write tool (§9.1 decision 1), `validate()` is called directly on an
already-parsed dict; `parse()`/`parse_file()` exist for file-based tests and any future paste
path.

**Schedule parsing** — a new pure module `api/webui/deck_schedule.py` for the bell/day/teacher
schedule formats and the `resolve_day()` resolver, with its IO layer added to
`api/webui/deps.py` beside the existing `list_calendar_files()`. Related existing code worth
reading first, none of which should be duplicated: `api/webui/calendar_csv.py` (academic-calendar
CSV parsing, two dialects, date-format tolerance) and `api/webui/schooldays.py` (holiday-aware
school-day math).

**Routes/templates/JS** — new `api/webui/routes/smartdeck.py` (`APIRouter`, included in
`server.py`), template `api/webui/templates/smartdeck.html` (extends `base.html`, implements
the 1/4 | 3/4 layout from §4), and JS under `api/webui/static/` for the management screen plus
the Display-mode client (clock-watching auto-advance from §3.1, widget interactivity, corner
chrome). The fullscreen Display view is a route in the same app on the same `127.0.0.1` bind
— no new server process.

**Feed resolution** — a new pure module (e.g. `api/deckforge_feeds.py`), parallel to the
existing `feedback_*.py` files, that reads Canvas Mirror and resolves Feed names into real
content. Called only server-side at Display/render time (§5.3) — never exposed to the AI.

**Storage** — a new top-level workspace folder `SmartDecks/`, parallel to the existing
`Quizzes/`, `Assignments/`, `Pages/`, `Rubrics/` author-facing folders:

```
<workspace>/SmartDecks/
    Decks/                 # per-day authored deck JSON (one file per date + revision)
    Deck Templates/
    Slide Templates/
```

Creating that folder costs one line: add `"SmartDecks"` to `WORKSPACE_SUBFOLDERS` in
`api/webui/workspace.py` (line 29) and `ensure_workspace()` both creates it and seeds it from
`api/default_docs/SmartDecks/` through the existing `_seed_folder_if_missing()` call. The same
generic seeding is what carries the real bell-schedule and Day Calendar CSVs from
`api/default_docs/Calendars/` into the workspace — the §6 carve-out therefore needs **no code
at all**, only files.

Bell schedules and the Day Calendar (`date -> schedule_id`) join the existing `Calendars/`
folder, consistent with how that folder is already the data-driven home for school-calendar
CSVs. The Teacher Schedule is JSON under `SmartDecks/` (§9.1 decision 3) — it has nested
combined-block structure that CSV expresses badly, and unlike the bell schedule it is
per-teacher config, so only a placeholder template ships in-repo.

Two existing primitives the write path must reuse rather than reinvent:
`workspace.path_within_workspace()` (realpath + commonpath — the path jail) and
`workspace.write_assignment_evidence_manifest()` (the mkstemp → fsync → `os.replace` atomic
write).

---

## 8. DeckForge contract

`LLM_Modules/DeckForge_Base.md` does not exist yet. Per the repo's own rule ("Authoring
contracts live in `LLM_Modules/*_Base.md`. These are canonical. `api/` *consumes* them —
never fork or 'fix' a contract by editing backend code"), this document should **not**
attempt to write that contract — it belongs in its own file, written with the same rigor as
`QuizForge_Base.md` et al. This design doc fixes the contract's *name* and its *inputs/outputs
at a high level* (§2, §5, §7); the field-by-field JSON schema is Open Item 2 below.

---

## 9. Implementation plan

Decisions taken 2026-07-30 in a planning pass over the actual code, and the slice files they
produced. The slice files are the build instructions; this section is the record of *why*
they're shaped that way.

### 9.1 Decision log

| # | Decision | Consequence |
|---|---|---|
| 1 | **AI authors via MCP write tools** (`save_deck`), not a paste-envelope UI | First write path on a server that is read-only today. `df.validate()` runs server-side inside the tool. Both MCP docstrings claiming "read-only" must be corrected. |
| 2 | **Slice 1 is feed-free** | Schedules, storage, contract, UI, and Display all land with **zero** PII surface. Feeds and Canvas Mirror resolution are deferred to a later slice with its own review. |
| 3 | **Hybrid schedule formats** | Bell Schedules + Day Calendar as CSV in `Calendars/` (flat, Excel-editable, next to the calendars they relate to). Teacher Schedule as JSON in `SmartDecks/` — combined blocks are nested and CSV mangles them. |
| 4 | **Timer is the only v1 widget** | One widget proves deck-scope vs. slide-scope lifecycle and the touch chrome. Later widgets are additions to a proven seam. A student *picker* is explicitly out — it needs roster data and would breach the feed-free boundary. |
| 5 | **Path jail only, no consent gate** | `save_deck` writes immediately, jailed to `<workspace>/SmartDecks/`, never overwriting. **The teacher's Display click is the human gate** — nothing auto-projects. No pending tray, no settings toggle. |
| 6 | **SmartDeck is a 7th primary nav item** | `nav_section = 'smartdeck'` → `/smartdeck`. It's a daily-use projector tool, not a sub-task of Create. |
| 7 | **Day Calendar ↔ academic calendar cross-validation deferred** | Slice 1 resolves `date → schedule_id → times` and shows a clean empty state for an unmapped date. The holiday-collision check is a later slice. |
| 8 | **Delete is non-destructive** | `delete_deck` moves the file to `_System/Archive/SmartDecks/`; it never unlinks. Deviation from a literal "Delete," justified by `workspace.py`'s non-destructive ethos and the fact that decks are teacher-authored work in a synced folder. The button may still say Delete. |

### 9.2 Slice files

Build in order; 3 and 4 can run in parallel once 2 lands.

| Slice | File | Lane |
|---|---|---|
| 1 — schedule data + resolver | `docs/handoffs/smartdeck-slice1-schedules.md` | Toyota |
| 2 — contract, `df.py`, MCP write surface | `docs/handoffs/smartdeck-slice2-contract-and-writes.md` | Toyota, **Ferrari review before merge** |
| 3 — management screen | `docs/handoffs/smartdeck-slice3-management-ui.md` | Toyota |
| 4 — Display view, auto-advance, timer | `docs/handoffs/smartdeck-slice4-display-and-timer.md` | Toyota |

### 9.3 Resolved: the §3.1 / §5.3 seam

Client-side auto-advance and server-side content resolution only coexist if the Display route
ships the **entire deck, fully resolved, in one payload** — every slide, every widget, every
resolved start/end time, inlined in the initial HTML, with zero fetches afterward. That is now
a hard requirement in slice 4. It also bounds §3.2's snapshot semantics: content freezes for
the whole deck at the moment Display is clicked, not per slide as each comes up.

### 9.4 Still open

1. **Custom widget authoring mechanism.** v1 ships the timer; the "let advanced users author
   their own" extensibility model (plugin API? sandboxed HTML/JS snippet?) is not designed.
   Nothing in slices 1–4 forecloses it.
2. **Onboarding/setup flow.** Slices 1–4 assume the three schedule files exist and render a
   static "not set up yet" panel plus a `readiness.py` probe when they don't. A real first-run
   flow — possibly a step in the existing `/welcome` wizard
   (`api/webui/routes/onboarding.py`) — is unscoped.
3. **Display chrome specifics.** Slice 4 fixes the *behavior* (persistent, reachable,
   Maximize/Minimize/Close, ≥44px touch targets); the exact icon set is still a design call.
4. **Feeds.** The whole of §5 is unimplemented by design. The feed catalog, the closed-allowlist
   validation, and `deckforge_feeds.py` resolution against Canvas Mirror are a future slice,
   and that slice is the one that needs a real Ferrari-lane privacy review — `slide.feed` is
   reserved in the v1 contract and rejected by `df.validate()` so adding it later is not a
   breaking change.
