# Handoff: remaining work on teacher-owned Panel themes

**Status of the feature: built, tested, green.** Teacher-owned Panel themes shipped in a
prior session, full suite `1991 passed`. This is the complete list of what is still
outstanding: one correction, one real bug fix, cleanup of artifacts already in the world,
and one documentation unit. Nothing here redesigns the feature.

**Executor:** one well-scoped implementer for Units 1, 2, 3, 5. Unit 4's second half needs
an assistant session holding the DesignSync tool and is marked as such.

**This document is self-contained.** Every palette, hex, hash, code block, and file body
you need is here. Do not round-trip.

---

## What already shipped, do not redo

| Piece | Where |
|---|---|
| Format, colour maths, contrast correction, CSS generation, storage | `api/panel_themes.py` |
| Themes folder path | `workspace.panel_themes_dir()`, created by `ensure_workspace()` |
| Custom keys resolve; generated stylesheet route | `api/webui/routes/panels.py`, `GET /panels/themes.css` |
| Stylesheet linked in all 9 Panel templates | `api/webui/templates/panel_*.html` |
| Console dropdown (Built in / Yours), skipped-file notice, help note | `api/webui/templates/panels.html`, `static/pages/panels.css` |
| 5 MCP tools at schema v23 | `api/mcp_server/tools.py`, `server.py`, `contract.py`, `tool_schema_v23.json` |
| Claude Design bundle + import path | `tools/design_theme_studio.py`, `tools/manifests/design-theme-studio.json`, `tools/TOOLS.md` |
| Tests | `api/tests/test_panel_themes.py` (71 tests), baselines in `test_beta075_mcp.py`, `test_mcp_server_tools.py`, `test_route_contract.py` |
| Docs | `docs/reference/panels-route-card.md` Themes section, `docs/mcp-server.md` |

The model in one paragraph: a theme is a JSON file at `Library/Panels/Themes/<key>.json`
holding `key`, `label`, `font`, `ornament`, and three or four colours (`bg`, `ink`,
`accent`, optional `highlight`). The server derives the other sixteen CSS variables,
corrects every text-on-background pairing to at least 4.5:1, and generates the CSS. Fonts
and ornaments are closed sets. Built-in keys cannot be shadowed. At most 24 custom themes.
A malformed file is skipped with a reason, never fatal.

---

## Why this handoff exists

The feature shipped with a demo theme called "Bobcat maroon". The school's colours are
navy, red, and white; **maroon is the rival's colour**. That is not merely a badly named
demo file: the maroon palette is the worked example inside `get_theme_contract`, which is
the first thing a connected assistant reads before authoring any theme, so every theme an
assistant proposed would start from the rival's palette. It is also in the teacher-facing
help copy in the Panels console, in the design-studio starter, and in a card already
pushed to a Claude Design project.

While deriving the correct navy/red/white values, a genuine defect surfaced in
`panel_themes.derive()`. On a near-white background, which is exactly what a school with
white in its colours picks, the derived row colours collapse into the page:

| authored `bg` | derived `--row` / `--row-alt` today |
|---|---|
| `#ffffff` | `#ffffff` / `#ffffff` (banding gone entirely) |
| `#f6f8fb` | `#fbfcfd` / `#f9fafc` (one to two shades, invisible on a projector) |

Rows lift toward white and hit the ceiling, so the banding that separates one row from the
next silently disappears. Fix that first, because the new themes land on exactly that
background.

---

## Decisions, already settled. Do not reopen.

- Ship the Bobcats palette **in the repo**. The teacher accepted that this reaches the
  public `main` snapshot.
- **Two themes**: one light, one dark.
- Hexes: navy `#123a70`, ink navy-black `#101c30`, red `#c8102e`.
- The two themes ship as **seeded theme JSON files**, not as new built-ins.
  `ensure_workspace()` already seeds `api/default_docs/Panels` into `Library/Panels`
  recursively and skips files that already exist
  ([workspace.py:693](api/webui/workspace.py:693), `os.walk` + `shutil.copy2`), so this
  needs no seeder change, no `BUILTIN_THEMES` change, no hand-written CSS, and no
  "eight built-ins" doc churn. The themes arrive as the teacher's own files: editable,
  deletable, exercising the same code path any teacher theme uses. **Built-in count stays
  eight.**

---

## Unit 1: fix the row banding. Do this first.

In `derive()` in [api/panel_themes.py](api/panel_themes.py), replace this exact block:

```python
    white = (255, 255, 255)
    light_surface = luminance(bg) > 0.4

    # Rows lift away from the page on a light theme and toward the light on a
    # dark one, which is the move every built-in theme makes by hand.
    if light_surface:
        row = mix(bg, white, 0.60)
        row_alt = mix(bg, white, 0.28)
    else:
        row = mix(bg, white, 0.070)
        row_alt = mix(bg, white, 0.035)
```

with:

```python
    white = (255, 255, 255)
    light_surface = luminance(bg) > 0.4

    # Rows lift away from the page on a light theme and toward the light on a
    # dark one, which is the move every built-in theme makes by hand. On a page
    # already at the top of its range there is nothing left to lift into, so
    # rows step down instead: a near-white theme that kept lifting would derive
    # --row and --row-alt equal to --bg and lose the banding that separates one
    # row from the next.
    if light_surface and 255 - max(bg) >= 12:
        row = mix(bg, white, 0.60)
        row_alt = mix(bg, white, 0.28)
    elif light_surface:
        row = mix(bg, ink_raw, 0.035)
        row_alt = mix(bg, ink_raw, 0.070)
    else:
        row = mix(bg, white, 0.070)
        row_alt = mix(bg, white, 0.035)
```

`ink_raw` is already in scope there. Verified: `bg #ffffff` then yields `row #f7f7f8`,
`row_alt #eeeff1`. Dark and mid-tone backgrounds are unchanged.

The constants are not the contract; the property is. Add to
[api/tests/test_panel_themes.py](api/tests/test_panel_themes.py):

```python
@pytest.mark.parametrize("bg", ["#ffffff", "#fffefd", "#f8fafc", "#f4efe6",
                                "#808080", "#0d1b33", "#000000"])
def test_rows_stay_distinguishable_from_the_page_at_any_lightness(bg):
    """Rows are the opaque bed row text sits on. If they collapse into --bg the
    banding that separates one row from the next is gone, and a projector shows
    one undifferentiated block. Near-white pages used to do exactly that."""
```

For each background pick an ink suited to its lightness (dark ink on a light page and the
reverse), then assert at least 3 per channel of separation between `--bg` and `--row`, and
between `--row` and `--row-alt`, and that `--ink` still clears `CONTRAST_FLOOR` against
all three.

Expected knock-on, not a failure: the `GOOD` fixture (`bg #f7f2ef`, headroom 8) crosses
into the darken branch, so its rows change from faintly lighter to faintly darker bands.
Nothing in the suite pins a derived row colour.

---

## Unit 2: ship the two Bobcats themes

Create `api/default_docs/Panels/Themes/` with the two files below.

Red sits in `highlight`, not `accent`, deliberately. `--today-accent` then keeps
essentially true red (`#c8102e` light, `#ca1734` night) for the emphasis bar, and only the
small red *text* on the tinted today row is darkened to clear 4.5:1. Red as the accent
would push the title and footer red much harder, and on the dark theme would read coral
rather than red. Do not swap them.

`api/default_docs/Panels/Themes/bobcats.json`:

```json
{
  "version": 1,
  "key": "bobcats",
  "label": "Bobcats",
  "font": "sans",
  "ornament": "grid",
  "colors": {
    "bg": "#f8fafc",
    "ink": "#101c30",
    "accent": "#123a70",
    "highlight": "#c8102e"
  },
  "authored_at": "2026-08-02T00:00:00+00:00",
  "authored_by": "canvasexpert"
}
```

`api/default_docs/Panels/Themes/bobcats-night.json`:

```json
{
  "version": 1,
  "key": "bobcats-night",
  "label": "Bobcats night",
  "font": "sans",
  "ornament": "glow",
  "colors": {
    "bg": "#0d1b33",
    "ink": "#eef2f8",
    "accent": "#7fb2ff",
    "highlight": "#c8102e"
  },
  "authored_at": "2026-08-02T00:00:00+00:00",
  "authored_by": "canvasexpert"
}
```

The night accent is navy lightened rather than navy itself, because navy on navy cannot
clear the reading floor.

Measured before Unit 1: light worst pairing 4.57:1, night 4.53:1, one corrected variable
each. Re-check both after Unit 1:

```bash
py -c "from api import panel_themes as p, json; [print(f, p.derive(p.normalize_theme(json.load(open(f))))['worst_pair'], p.derive(p.normalize_theme(json.load(open(f))))['worst_ratio']) for f in ['api/default_docs/Panels/Themes/bobcats.json','api/default_docs/Panels/Themes/bobcats-night.json']]"
```

Add a test that both seeded files parse, derive, and clear `CONTRAST_FLOOR`, so a future
derivation change cannot quietly make a shipped theme illegible.

---

## Unit 3: remove maroon from source, UI, tests, and docs

| File | Change |
|---|---|
| [api/mcp_server/tools.py:926](api/mcp_server/tools.py:926) | The `get_theme_contract` `example` block becomes the `bobcats` palette: key `bobcats`, label `Bobcats`, font `sans`, ornament `grid`, colours as above. **Highest-value line here:** it is what an assistant copies. |
| [tools/design_theme_studio.py:291](tools/design_theme_studio.py:291) | `STARTER` colours become the `bobcats` palette. Leave its key and label starter-flavoured. |
| [api/webui/templates/panels.html:61](api/webui/templates/panels.html:61) | Help copy currently suggests `"a maroon and gold theme with a quiet grid"`. Use a palette that is neither maroon nor the shipped Bobcats one, so the example still reads as "ask for anything", e.g. `"a green and cream theme with a quiet grid"`. Add a clause noting the two Bobcats themes come with the app and can be edited or deleted. Relaxed tone, no compliance-banner voice, no em-dashes. |
| [api/panel_themes.py:134](api/panel_themes.py:134) | Error message example hex `#7c1d2e` becomes `#123a70`. |
| [api/tests/test_panel_themes.py](api/tests/test_panel_themes.py) | The `GOOD` fixture palette becomes the navy/red values; the `bobcat-maroon` key in the MCP round-trip test becomes a neutral key such as `test-navy`. |
| [docs/reference/panels-route-card.md](docs/reference/panels-route-card.md) | In the Themes section, note that two Bobcats themes seed into `Library/Panels/Themes` on first run and are the teacher's to edit or delete. Built-in count stays eight. |

Grep gate when finished:

```bash
rg -i "maroon|7c1d2e|c8a24a|b08422" --glob '!out/**'
```

Only unrelated hits under `docs/handoffs/senior level/` (historical Panels initiative
notes) should remain.

---

## Unit 4: clean up the artifacts already in the world

- **The teacher's synced workspace** holds a real `bobcat-maroon.json` from the earlier
  verification run, at `<workspace>\Library\Panels\Themes\bobcat-maroon.json`. Remove it:
  ```bash
  py -c "from api import panel_themes; print(panel_themes.delete_theme('bobcat-maroon'))"
  ```
  Then run the app once so `ensure_workspace()` seeds the two new themes, and confirm both
  appear under "Yours" in `/panels`.

- **The Claude Design project** "CanvasExpert Panel Themes"
  (`36c21d56-ddfd-4006-bc89-4690c4818954`) holds `yours-bobcat-maroon.html` and a
  `starter.html` embedding the maroon palette. Regenerate with
  `py tools/design_theme_studio.py build`, then the maroon card must be **deleted** from
  the project and `starter.html` plus the new `yours-bobcats*.html` cards re-pushed.
  **Needs an assistant session with the DesignSync tool; a local implementer cannot do
  this half.** Leaving the maroon card orphaned reproduces the original bug in a second
  place.

---

## Unit 5: describe Panels and the theme tools in the CanvasAgent instruction set

`api/default_docs/AI Authoring/START HERE - CanvasAgent.txt` is the single canonical file
teachers paste into their own AI. It currently says nothing about Panels or Panel themes,
so a connected assistant does not know the theme tools exist and will tell a teacher the
feature is not real.

### Step 1, easy to forget: retire the current hash first

This is a same-name-update file. A teacher's synced copy refreshes only when its old hash
is listed as retired, so **before editing**, add the current shipped hash to
`RETIRED_FILES` in [api/webui/ai_ta.py](api/webui/ai_ta.py):

```python
    "START HERE - CanvasAgent.txt": frozenset({
        # First release, before the procedure-first rewrite.
        "66fb445401ff147e03b727d01d70e08f8337563f94d954ef6ac6fae9dfa0706b",
        # Procedure-first rewrite, before Appendix A on installing and running.
        "e5e4023c419e14de58339f32c3b6da5bafd81528aae91d41477640c5f27b21b6",
        # Before the scoring packet MCP tools were described.
        "94788ae4a8c063cd2e60f234e51a3f902e8fed8282b10caba80121135c8fb80b",
        # Before Panels and the Panel theme tools were described.
        "52f9755e202e51072cb687df1a0d1fa6b85d468dd371d7f8c30bd73e4c3656fe",
    }),
```

That last hash is the file's current content, verified.
`test_a_retired_name_that_still_ships_cannot_churn` fails if you list a hash that is still
current, so add the old hash and then edit, in that order. To recover it if you edit first:

```bash
git stash && py -c "from api.webui import ai_ta; from pathlib import Path; print(ai_ta._shipped_hash(Path('api/default_docs/AI Authoring/START HERE - CanvasAgent.txt').read_bytes()))" && git stash pop
```

### Step 2: constraints, enforced by `api/tests/test_canvasagent_instructions.py`

- **The CORE block is full.** Budget 1500 chars, currently 1485, so **15 chars of
  headroom**. Put nothing new in CORE. All new text goes in an appendix.
- **No em-dashes, no smart punctuation, ASCII only.**
- **Every MCP tool name you write must be a real registered tool.** The five are
  `get_theme_contract`, `list_panel_themes`, `preview_panel_theme`, `apply_panel_theme`,
  `delete_panel_theme`.
- Do not add or rename an appendix; CORE routes to every appendix by name and the test
  checks that mapping.

### Step 3: Appendix B, what CanvasExpert can do

Insert after the `PowerGrader.` paragraph block (the one listing the three grading mode
names) and before the paragraph that currently follows it:

```
Panels. One URL that renders one thing, full bleed, for a projector or a
classroom screen. What is due, a random student, missing work, birthdays,
upcoming events, today's objective. Each one reads local data only, never live
Canvas, because it runs unattended on a wall for a whole period. A teacher
pastes the URL into whatever display surface they already use.

Panel themes. Eight themes ship, plus two in the teacher's colours they can
edit or delete. A teacher can also keep their own, as small JSON files in
Library/Panels/Themes, which follow their sync between machines. A theme is a
palette, a typeface, and one decorative layer: it can never change what a Panel
shows or how many rows fit. The teacher picks a background, an ink, an accent,
and optionally a highlight colour; CanvasExpert derives the rest and corrects
any pairing that would not stay readable from the back of a room.
```

### Step 4: Appendix D, when CanvasExpert is connected as a tool provider

Add one bullet to the existing `Sequence matters:` list, directly after the
`list_staged_content(kind)` bullet and before `Prefer narrow reads.`, so the read-ordering
advice stays last:

```
  * get_theme_contract() before offering to build a Panel theme. Then
    preview_panel_theme(key, label, colors), read back what it corrected and
    tell the teacher, and apply_panel_theme(preview, digest) to save it.
    list_panel_themes() shows what they already have, delete_panel_theme(key)
    removes one of theirs. Built-in themes are not yours to change. Colours are
    hex only, and the font and ornament names come from the contract, so do not
    invent either.
```

If the teacher asks why a colour came out different from the one they named, the answer is
contrast: a Panel is read from the back of a room, so text colours are corrected to a
4.5:1 floor and the preview reports every move.

---

## Verification gate

```bash
py -m pytest api/tests/test_panel_themes.py api/tests/test_panels.py api/tests/test_canvasagent_instructions.py api/tests/test_ai_ta.py -q
```

```bash
py -m pytest api/tests -q
```

Baseline was `1991 passed`; expect that plus the new tests. The full run matters here
because the workspace-tree tests touch seeded folders and the instruction file is served by
a route and hashed by the seeder.

If `test_every_mcp_tool_named_is_a_real_tool` fails you mistyped a tool name. If
`test_stays_ascii` or `test_no_em_dashes_or_smart_punctuation` fails you pasted a smart
quote or dash from this document's prose rather than from its code blocks.

The row fix is a rendered property, so confirm it rendered rather than only computed. Start
the verify server (`.claude/launch.json` entry `canvas-expert-verify`, port 8766) and:

1. Load `/panels/upcoming-events?theme=bobcats`. Read back resolved `--bg`, `--row`,
   `--row-alt`, and the computed background of `.p-row` elements. The three must be visibly
   distinct, not merely unequal. Repeat for `?theme=bobcats-night`.
2. Re-confirm the theme law with the new themes in play: measure `.p-body` height for `ce`,
   `bobcats`, `bobcats-night`, and an unknown key at one fixed viewport. All four must
   match exactly, and the unknown key must fall back to `ce` with a 200. A theme that moved
   that box would change what a Panel shows, not just how it looks.
3. `/panels` console: both Bobcats themes under "Yours", and no "maroon" in the page text.

---

## Not in scope

Leave these alone unless separately asked. Each was considered and decided.

- **The visual theme editor in the Panels console.** The choice was AI-authors-the-file
  first, editor as a later slice once the format proved out. It has now proved out, so this
  is the natural next slice.
- **A "duplicate a built-in and tweak it" affordance.** Built-ins are hand-written CSS with
  richer palettes than the authored four-slot format, so duplicating one is lossy.
  `tools/design_theme_studio.py` ships a starter card instead.
- **Live theme reload on an open board.** The generated stylesheet is sent `no-store`, but a
  projector board already open keeps the CSS it fetched until something reloads it.
  Accepted, and documented in the Panels route card.
- **Any change to the eight built-in themes.** They stay hand-written CSS in
  `static/panels/themes.css`.
- **Re-deriving built-in palettes into the authored four-slot format.** Deliberately lossy.
