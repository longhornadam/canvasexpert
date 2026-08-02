# Handoff: Panel theme art (any image), plus the contrast bug the last pass hid

**Two units, in this order.** Unit A is a small correctness fix with a known-good answer.
Unit B is the feature: let a teacher drop a picture into a folder and have it become their
theme's decoration, with no file-size or file-type homework.

**Executor:** one implementer for Units A and B. Two leftovers at the end need an assistant
session holding the DesignSync tool and are marked as such.

**Self-contained.** Every constant, code block, and measured number you need is here.

**Guiding constraint for Unit B, from the teacher who owns this tool:** *"It Just Works.
This is for teachers, not designers or techies."* A teacher should never be asked to think
about file size, file format, or resolution. Every limit in this document is one the code
absorbs silently, not one the teacher is told about. Where something genuinely cannot look
good, we say one plain sentence about it and still render.

---

## Context

Teacher-owned Panel themes shipped and are green (`2000 passed`). A theme is a JSON file in
`Library/Panels/Themes/<key>.json` carrying `key`, `label`, `font`, `ornament`, and three or
four colours. `api/panel_themes.py` derives the other sixteen CSS variables, corrects
contrast, and generates CSS served at `GET /panels/themes.css`.

Two things bring you here.

**The decoration layer is closed.** `ornament` picks from eight gradient recipes. Meanwhile
four built-in themes already carry real artwork: `natural` has hand-drawn leaves, `ocean` a
whale, `cottage` flowers, `lisa` stars, all inline SVG data URIs hand-written into
`themes.css`. So per-theme art is not new capability. What is missing is a path from *a
teacher's own file* to that same layer. Teachers want a leaf for a nature theme and an
octopus for an ocean theme, and LLM-drafted SVG is not good enough to substitute. The
assistant's job here is placing art, not drawing it.

**The previous pass hid a real bug.** `api/tests/test_panel_themes.py` now carries a comment
claiming a mid-grey page "cannot clear 4.5:1 with any ink … so the floor is only owed where
the system can actually reach it", guarded by a conditional assertion. That claim is false
and the conditional hides a genuine defect. Unit A fixes it.

---

## Unit A: correct contrast against every bed, not just the first

### The defect

`derive()` corrects a text colour with:

```python
    def corrected(name, colour, backgrounds, target=CONTRAST_FLOOR):
        bed = _worst(colour, backgrounds)
        fixed, moved = toward_contrast(colour, bed, target)
```

It picks the single worst bed **using the original colour**, then `toward_contrast` stops as
soon as that one bed clears. Moving the colour reorders which bed is worst, so the result can
stop short on a different bed. `--ink`, `--muted`, and `--warn-ink` are corrected against
three beds (`--bg`, `--row`, `--row-alt`) and are all exposed. `--title`, `--accent`,
`--pill-ink`, and `--today-ink` use a single bed and are fine.

Measured: sweeping greyscale backgrounds, **5 of 16 report a `worst_ratio` below the
advertised 4.5 floor**.

```
#606060  --warn-ink on --row   4.19
#707070  --muted on --row      3.94
#808080  --ink on --bg         4.04
#909090  --ink on --bg         4.13
#a0a0a0  --ink on --bg         4.21
```

The floor is reachable in every one of those cases. On `#808080`, ink `#151616` gives
4.59 / 5.18 / 4.85 against bg / row / row-alt. The system simply aims wrong.

### The fix

Add a multi-bed helper beside `toward_contrast` in [api/panel_themes.py](api/panel_themes.py).
Leave `toward_contrast` in place; it is the single-bed primitive and is tested directly.

```python
def toward_contrast_all(foreground, backgrounds, target):
    """Push a text colour until it clears ``target`` against EVERY bed it can
    land on.

    Correcting against only the worst bed is not enough: moving the colour
    reorders which bed is worst, so a colour aimed at one bed can stop just
    short on another. Rows sit within a few steps of the page, so all three
    beds are on the same side of the text and one direction raises contrast
    against all of them at once.
    """
    beds = list(backgrounds)
    if all(contrast(foreground, bed) >= target for bed in beds):
        return foreground, False
    reference = _worst(foreground, beds)
    black, white = (0, 0, 0), (255, 255, 255)
    goal = black if contrast(black, reference) >= contrast(white, reference) else white
    candidate = foreground
    for step in range(1, 101):
        candidate = mix(foreground, goal, step / 100)
        if all(contrast(candidate, bed) >= target for bed in beds):
            return candidate, True
    return candidate, True
```

Then `corrected()` inside `derive()` becomes:

```python
    def corrected(name, colour, backgrounds, target=CONTRAST_FLOOR):
        fixed, moved = toward_contrast_all(colour, backgrounds, target)
        if moved:
            bed = _worst(fixed, backgrounds)
            adjustments.append({
                "variable": name,
                "from": to_hex(colour),
                "to": to_hex(fixed),
                "against": to_hex(bed),
                "ratio": round(contrast(fixed, bed), 2),
                "floor": target,
            })
        return fixed
```

Report `against` as the bed that is worst *after* the move, since that is the pairing the
reported ratio describes.

### Test changes

1. In `test_rows_stay_distinguishable_from_the_page_at_any_lightness`, **delete the
   conditional and the comment** that claims the floor is unreachable. Assert `--ink` clears
   `CONTRAST_FLOOR` against all three beds unconditionally.
2. Add the regression test that would have caught this:

```python
@pytest.mark.parametrize("level", range(0, 256, 16))
def test_no_page_lightness_reports_below_the_floor(level):
    """derive() promises a 4.5:1 floor. Correcting against only the worst bed
    used to under-shoot on mid-tone pages, so the promise and the reported
    worst_ratio disagreed."""
```

Build a greyscale `bg` from `level`, pick an ink by lightness the same way the row test does,
and assert `derive(...)["worst_ratio"] >= CONTRAST_FLOOR`. Expect 16 of 16 passing after the
fix.

Both shipped Bobcats themes are already above the floor (4.57 and 4.53), so nothing on a wall
changes.

---

## Unit B: theme art

### What a teacher does

Drop a picture into `Library/Panels/Themes/art/`. That is the whole interaction. Either name
it after a theme (`art/bobcats.svg`) and it attaches by itself, or ask the assistant to place
it. No sizes, no formats, no settings.

### Accepted files

`.svg`, `.png`, `.jpg`, `.jpeg`, `.webp`. Not SVG-only: teachers have PNGs far more often,
and a logo PNG in a corner on a projector is genuinely fine. Pillow is already a declared
dependency (`Pillow>=10.0` in `api/requirements.txt`, lazily imported at
[student_attachments.py:113](api/powergrader/student_attachments.py:113)) so raster handling
adds no install and has an existing pattern to follow. Lazy-import it the same way.

### Format

New optional `art` list on a theme, alongside the existing `ornament`:

```json
{
  "key": "ocean-life",
  "label": "Ocean life",
  "font": "sans",
  "ornament": "scanlines",
  "colors": { "bg": "#eaf4fa", "ink": "#10293b", "accent": "#1a7fae", "highlight": "#e08a1e" },
  "art": [
    { "file": "octopus.svg", "place": "corner-br", "size": 22, "opacity": 0.5, "recolor": "accent" },
    { "file": "bubbles.svg", "place": "scatter",   "size": 8,  "opacity": 0.35, "recolor": "highlight" }
  ]
}
```

Field rules:

- `file`: a filename only. Refuse anything containing `/`, `\`, or `..`, the same discipline
  as theme keys. Must exist in the art folder.
- `place`: closed set, listed below. This is the part that means a teacher never writes
  `no-repeat left -3vmin top -4vmin / 18vmin`.
- `size`: vmin, clamped 4 to 80. Ignored for `cover`.
- `opacity`: clamped 0.05 to 1.0. Default 0.5.
- `recolor`: `accent` (default), `ink`, `highlight`, `bg`, or `none`. SVG only; silently
  ignored for raster rather than refused.
- Add `art` to `ROOT_KEYS`. Keep unknown-field rejection as-is.

### Placement vocabulary

Each entry compiles to one or more background layers. Art layers come **first** in the
`--ornament` value so they sit above the gradient recipe, which is how `natural` composes its
leaves over a radial gradient today.

| `place` | background shorthand |
|---|---|
| `corner-tl` | `no-repeat left -2vmin top -3vmin / <size>vmin` |
| `corner-tr` | `no-repeat right -2vmin top -3vmin / <size>vmin` |
| `corner-bl` | `no-repeat left -2vmin bottom -3vmin / <size>vmin` |
| `corner-br` | `no-repeat right -2vmin bottom -3vmin / <size>vmin` |
| `scatter` | three layers from one entry: `left 6% top 9% / <size>vmin`, `right 8% top 38% / <size*0.7>vmin`, `left 22% bottom 11% / <size*0.85>vmin`, each `no-repeat` |
| `tile` | `repeat 0 0 / <size>vmin <size>vmin` |
| `band-bottom` | `repeat-x left bottom / auto <size>vmin` |
| `watermark` | `no-repeat center / <size>vmin` |
| `cover` | `no-repeat center / cover`, plus the scrim below |

**The `cover` scrim.** A full-bleed photo behind a nature theme is a thing teachers will
try, and it mostly works because `.p-row` is opaque. The exception is the title and footer,
which sit directly on `--bg`. So when any entry uses `cover`, emit an extra topmost gradient
layer of `--bg` at partial alpha (start at `0.55`) over the photo. The teacher drops in a
forest photo and the header stays readable without knowing why.

### Ingest: where the "just works" actually happens

Process each art file once, cache the result, and serve the cached bytes. Nothing here is
surfaced to the teacher as a limit.

**SVG.** Parse with `xml.etree.ElementTree` (stdlib) and re-serialize from the parsed tree.
This is the same emit-never-forward discipline the colour code uses, and here it is what
enables the features rather than a security posture:

- Drop editor cruft: `sodipodi` and `inkscape` namespaced elements and attributes,
  `<metadata>`, comments. A 12MB Illustrator export is mostly this.
- Round every numeric literal in `d`, `points`, and coordinate attributes to 2 decimals.
  Together with the above this is routinely a 10x to 50x reduction with no visible change.
- Keep gradients, `<style>`, and `<image>` with embedded data. An embedded raster inside a
  traced logo is a normal thing a teacher has and must not be stripped.
- `recolor`: replace every `fill` and `stroke` value that is not `none` with the derived
  palette hex. This is what makes a downloaded black icon land on-palette instantly, and it
  is the single highest-value part of this unit for stock art.
- `opacity`: wrap the document contents in `<g opacity="...">`. CSS cannot set per-layer
  background opacity, so bake it in.
- Require a `viewBox`. Without one the art cannot scale to a projector. Report rather than
  refuse (see diagnostics).

**Raster.** Open with Pillow, downscale anything larger than 1600px on its longest side (no
placement can use more), multiply the alpha channel by `opacity`, and save: PNG when there is
an alpha channel, JPEG at quality 85 when there is not. `recolor` does not apply.

**Cache location matters.** Write processed bytes to the **local app dir**, not the synced
workspace: `runtime_paths.local_app_dir() / "panel-art-cache"`. Derived bytes in a synced
folder would churn OneDrive for no reason. Key the cache on source path, mtime, size, and the
entry's `opacity`, `recolor`, and `place`, since the output depends on all of them. Rebuild
when the key changes. This is the only reason a 12MB source file is free: it is parsed once,
not per request.

### Serving

`GET /panels/theme-art/{key}/{index}.{ext}` returns the cached processed bytes with
`Cache-Control: public, max-age=31536000, immutable`. The generated CSS references it with a
content hash: `url("/panels/theme-art/ocean-life/0.svg?v=<hash>")`.

A route, not a data URI. Inlining would put art into a stylesheet sent `no-store`, so a board
with nine panels would re-download it nine times per load. A hashed immutable URL is fetched
once and cached, which is what makes file size stop mattering.

Path depth means no collision with the `/panels/{kind}` catch-all, but register it next to
`/panels/themes.css` anyway so the ordering rule stays in one place.

### Two changes this forces, both intentional

**1. The network invariant changes.** `test_no_ornament_can_reach_the_network` currently bans
`url(` outright. Replace it with a precise version: every `url(...)` in generated CSS must
match

```
^/panels/theme-art/[a-z0-9-]+/\d+\.(svg|png|jpe?g|webp)\?v=[0-9a-f]+$
```

and `http`, `//`, `@import`, `image-set`, and `src:` stay banned. Rename it to
`test_nothing_in_a_theme_can_reach_the_internet`. This is a real weakening of a guard, traded
knowingly: same-origin localhost reading a file off disk, exactly like `panel.css`. What must
not change is that a Panel on a wall never waits on the internet.

**2. Scope the stylesheet, drop the theme cap.** Make `GET /panels/themes.css` accept
`?theme=<key>` and return only that theme's block, falling back to all themes when the
parameter is absent so nothing existing breaks. Panel templates already have `theme` in
context, so the link becomes
`href="/panels/themes.css?theme={{ theme }}&v={{ asset_v }}"`.

With that, `MAX_CUSTOM_THEMES = 24` loses its rationale (it existed to bound stylesheet
payload) and should be removed. **This deletes two existing tests**,
`test_the_folder_has_a_ceiling` and
`test_apply_refuses_past_the_ceiling_but_still_allows_replacing`, and the ceiling clause in
`apply_preview`. Keep the per-file skip-and-report behaviour untouched; that is what protects
a saved board, not the count.

### Diagnostics: diagnose, never police

Art problems degrade to the theme's gradient ornament, never lose the theme, and get named in
the console next to the existing unreadable-theme-file notice. Each message is one plain
sentence with an obvious next step:

- **Too small for its placement.** Placements are vmin, so the needed pixels are computable:
  a 22vmin corner mark wants ~240px at 1080p and ~475px on a 4K TV; a 60vmin watermark wants
  ~650px and ~1300px. Say `"bobcat.png is 180px, good in a corner, soft as a watermark."`
  Never refuse.
- **JPG in a non-cover placement.** No alpha, so it lands as a rectangle rather than a shape:
  `"This photo has no transparent background, so it will show as a rectangle. Save it as a
  PNG with transparency, or use it as a full background."`
- **SVG pointing at an image on the web.** It will not load: browsers render background SVGs
  in a static mode with no external fetching. Say so plainly rather than silently showing
  nothing.
- **No `viewBox`.** `"This drawing has no size information, so it cannot scale to a
  projector."`
- **Unreadable or corrupt.** Drop the entry, name the file, keep the theme.

One thing that needs no decision: animation inside a background SVG (SMIL or CSS) does not
run in that same static mode. It simply sits still. Do not strip it; document the line.

### Zero-config attach

If a theme has no `art` and `art/<key>.<ext>` exists, synthesize one entry:
`place: "corner-br"`, `size: 22`, `opacity: 0.5`, `recolor: "accent"`. Dropping a file named
after your theme is then the entire setup.

### MCP and console

- New tool `list_theme_art()`: the files present, their kind, dimensions or viewBox, and any
  diagnostic above. The assistant references filenames that exist instead of inventing them.
- `preview_panel_theme` and `apply_panel_theme` accept the `art` list. `preview` reports the
  processed size, the placement it compiled to, and any diagnostic, so the assistant can tell
  the teacher what will happen before it happens.
- Extend `get_theme_contract` with the accepted extensions, the `place` vocabulary, the
  `size` and `opacity` ranges, `recolor`, and one line stating the assistant places art and
  does not draw it.
- The Panels console lists the art it found, with each file's diagnostic if any, beside the
  existing theme-problems notice.

### The design studio

[tools/design_theme_studio.py](tools/design_theme_studio.py) builds standalone cards that get
pushed to claude.ai/design, where `/panels/theme-art/...` will not resolve. So for cards
only, **inline the processed art as a data URI** rather than referencing the route. The app
uses the route; the cards inline. Note also that a card's embedded JSON references a filename
by name, so importing a card onto a machine that lacks that file reports the missing art and
keeps the theme.

### Tests

Cover at least: an `art` entry compiles to the expected background shorthand per `place`; art
layers precede gradient layers; `cover` emits the scrim; `recolor` uses the *derived* palette;
opacity is baked and clamped; a filename with `..` or a separator is refused; a missing file
degrades to the gradient ornament with a named problem; SVG cruft and coordinate rounding
actually shrink a fixture; a raster over 1600px is downscaled; the cache is keyed so changing
`recolor` regenerates; generated CSS matches the URL pattern above and still contains no
`http` or `//`; and the sizing law still holds, meaning a theme with art emits nothing but
custom properties.

---

## Verification gate

```bash
py -m pytest api/tests/test_panel_themes.py api/tests/test_panels.py -q
```

```bash
py -m pytest api/tests -q
```

Baseline is `2000 passed`, minus the two ceiling tests you delete, plus the new ones.

Art is a rendered feature, so prove it rendered. Start the verify server
(`.claude/launch.json` entry `canvas-expert-verify`, port 8766) with a real image dropped in
the art folder, then:

1. Load a panel with an art-bearing theme. Confirm the computed `body::before`
   `background-image` contains the `/panels/theme-art/...` URL, that the URL returns 200 with
   the immutable cache header, and that the art is visible.
2. **The sizing law, again.** Measure `.p-body` height for `ce`, an art-bearing theme, and an
   unknown key at one fixed viewport. All must match exactly. Art is decoration; if it moved
   that box it would change what a Panel shows.
3. Set a `cover` photo and confirm the title and footer stay readable over it, and that the
   scrim layer is present.
4. Shrink the panel below 320x210 and confirm ornament including art switches off, as it does
   today.
5. Drop a deliberately tiny PNG and a JPG in a corner placement, and confirm the console
   shows both diagnostics and the theme still renders.

---

## Leftovers from the previous handoff

Both need an assistant session with the DesignSync tool and are **not** the local
implementer's work:

- The Claude Design project "CanvasExpert Panel Themes"
  (`36c21d56-ddfd-4006-bc89-4690c4818954`) still holds `yours-bobcat-maroon.html` and a
  `starter.html` embedding the maroon palette. Delete the maroon card and re-push the
  regenerated bundle.
- After Unit B, regenerate and re-push so the cards show art.

---

## Not in scope

- The visual theme editor in the Panels console. Still the natural next slice, and art makes
  it more valuable: picking a corner and an opacity is exactly what a slider is for.
- Any change to the eight built-in themes. They keep their hand-written SVG data URIs.
- Video or animated GIF as art. A projector running one all period is a distraction, and
  neither works as a CSS background anyway.
- Cropping, masking, or any image editing beyond downscale, alpha, and recolour. If a teacher
  needs the logo cropped, they crop it before dropping it in.
