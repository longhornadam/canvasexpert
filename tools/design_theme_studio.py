"""Panel theme studio: build a Claude Design bundle, or import a card back.

Themes are small enough to author by hand and visual enough that comparing
them side by side is the only honest way to judge one. This script is the
bridge between the two places that happens:

* ``build`` writes a self-contained card per theme into
  ``out/design/panel-themes/``. Each card renders a mock Panel in that theme's
  real derived palette, prints its measured contrast, and (for a teacher's own
  themes) embeds the authored JSON that produced it. An assistant with the
  DesignSync tool pushes that folder to a claude.ai/design design-system
  project, where the cards can be viewed and edited together.

* ``import`` reads a card back, pulls the embedded JSON out of it, runs it
  through the same validation and contrast correction as any other theme, and
  writes it into the teacher's synced Library. That is what makes the design
  project a real source rather than a mood board: a theme designed there lands
  in the app without anybody retyping hex codes.

The network hop is deliberately not here. This script only ever touches the
local filesystem; the assistant holding the DesignSync tool does the pushing
and fetching, which keeps a credentialed API out of a script a teacher might
run by hand.

Usage, from the repository root:

    py tools/design_theme_studio.py build
    py tools/design_theme_studio.py import <card.html> [--apply]

``import`` prints what it found and refuses on anything invalid. Without
``--apply`` it is a dry run.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api import panel_themes                                    # noqa: E402
from api.platform_services import workspace                      # noqa: E402

OUT_DIR = REPO_ROOT / "out" / "design" / "panel-themes"
SOURCE_BLOCK_ID = "canvasexpert-theme"
BUILTIN_CSS = REPO_ROOT / "api" / "webui" / "static" / "panels" / "themes.css"

# The card viewport: a 16:9 board at the size a Panel actually gets dropped
# into, so what the Design System pane shows is the shape a teacher sees.
CARD_WIDTH, CARD_HEIGHT = 720, 405


def _builtin_variables() -> dict[str, dict[str, str]]:
    """Pull each built-in theme's declared custom properties out of themes.css.

    Built-ins are hand-written CSS, not authored JSON, so their cards are
    reference only: there is nothing to round-trip, and inventing a three
    colour approximation of ``lisa`` would just be a worse ``lisa``.
    """
    css = BUILTIN_CSS.read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found: dict[str, dict[str, str]] = {}
    for match in re.finditer(
            r'html\[data-panel-theme="([a-z0-9-]+)"\]\s*\{(.*?)\}', css, flags=re.S):
        key, block = match.group(1), match.group(2)
        variables = found.setdefault(key, {})
        for declaration in re.finditer(r"(--[a-z-]+)\s*:\s*([^;]+);", block, flags=re.S):
            variables[declaration.group(1)] = " ".join(declaration.group(2).split())
    return found


def _mock_panel(variables: dict[str, str], art_uris: dict[int, str] | None = None) -> str:
    """A Panel-shaped preview: header rule, four rows, one emphasised, a foot."""
    def var(name, fallback=""):
        return variables.get(name, fallback)

    ornament = var("--ornament", "none")
    # For cards, art is inlined as data URIs (the design project cannot reach
    # the local route). The app itself uses the route; only the cards inline.
    art_layers = ""
    if art_uris:
        art_layers = "".join(
            f'<div class="art" style="background-image:url(\'{uri}\')"></div>'
            for uri in art_uris.values())
    return f"""
<div class="board">
  <div class="ornament"></div>
  {art_layers}
  <div class="panel">
    <div class="head">
      <div class="title">What's due</div>
      <div class="sub">ELA 7 &middot; PERIOD 3</div>
    </div>
    <div class="body">
      <div class="row today">
        <span class="when">Today</span>
        <span class="name">Lantern essay, final draft</span>
        <span class="pill">10 pts</span>
      </div>
      <div class="row">
        <span class="when">Tue</span>
        <span class="name">Chapter 7 reading check</span>
        <span class="pill">5 pts</span>
      </div>
      <div class="row alt">
        <span class="when warn">Late</span>
        <span class="name">Vocabulary set 4</span>
        <span class="pill">8 pts</span>
      </div>
      <div class="row">
        <span class="when">Fri</span>
        <span class="name">Socratic seminar prep</span>
        <span class="pill">15 pts</span>
      </div>
    </div>
    <div class="foot">
      <span>CANVAS EXPERT</span>
      <span class="cta">UPDATED 8:02 AM</span>
    </div>
  </div>
</div>
<style>
  .board {{
    position: relative; width: 100%; max-width: {CARD_WIDTH}px;
    aspect-ratio: 16 / 9; overflow: hidden;
    background: {var('--bg', '#fff')};
    font-family: {var('--panel-font', 'system-ui, sans-serif')};
    border: 1px solid rgba(0,0,0,.15);
  }}
  .ornament {{
    position: absolute; inset: 0; z-index: 0; pointer-events: none;
    background: {ornament};
    opacity: {var('--ornament-opacity', '1')};
  }}
  .art {{
    position: absolute; inset: 0; z-index: 0; pointer-events: none;
    background-repeat: no-repeat; background-position: right bottom;
    background-size: 22vmin; opacity: .5;
  }}
  .panel {{
    position: relative; z-index: 1; height: 100%;
    display: flex; flex-direction: column; gap: 6px;
    padding: 16px 20px; color: {var('--ink', '#111')};
  }}
  .head {{
    display: flex; align-items: baseline; justify-content: space-between;
    gap: 12px; padding-bottom: 6px;
    border-bottom: 2px solid {var('--rule', 'rgba(0,0,0,.25)')};
  }}
  .title {{ font-size: 30px; font-weight: 800; letter-spacing: -.02em;
            color: {var('--title', var('--ink', '#111'))}; }}
  .sub {{ font-size: 11px; font-weight: 800; letter-spacing: .14em;
          color: {var('--muted', '#666')}; }}
  .body {{ flex: 1; display: flex; flex-direction: column; gap: 4px; justify-content: center; }}
  .row {{
    flex: 1; display: grid; grid-template-columns: 92px minmax(0, 1fr) auto;
    align-items: center; gap: 12px; padding: 0 10px; border-radius: 4px;
    background: {var('--row', 'transparent')}; font-size: 17px;
  }}
  .row.alt {{ background: {var('--row-alt', var('--row', 'transparent'))}; }}
  .row.today {{
    background: {var('--today-bg', var('--row', 'transparent'))};
    box-shadow: inset 4px 0 0 0 {var('--today-accent', var('--accent', 'transparent'))};
  }}
  .row.today .when, .row.today .name {{ color: {var('--today-ink', var('--ink', '#111'))}; }}
  .when {{ font-size: 13px; font-weight: 800; letter-spacing: .08em;
           text-transform: uppercase; color: {var('--when-ink', var('--muted', '#666'))}; }}
  .when.warn {{ color: {var('--warn-ink', var('--muted', '#666'))}; }}
  .name {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }}
  .pill {{
    justify-self: end; font-size: 12px; font-weight: 800;
    padding: 3px 10px; border-radius: 999px;
    background: {var('--pill-bg', 'transparent')}; color: {var('--pill-ink', var('--ink', '#111'))};
  }}
  .foot {{
    display: flex; justify-content: space-between; gap: 12px; padding-top: 6px;
    border-top: 2px solid {var('--rule', 'rgba(0,0,0,.25)')};
    font-size: 10px; font-weight: 800; letter-spacing: .15em;
    color: {var('--muted', '#666')};
  }}
  .cta {{ color: {var('--accent', 'inherit')}; }}
</style>
"""


def _swatches(variables: dict[str, str]) -> str:
    rows = []
    for name in sorted(variables):
        value = variables[name]
        if name in ("--panel-font", "--ornament", "--ornament-opacity"):
            continue
        rows.append(
            f'<li><span class="chip" style="background: {html.escape(value)}"></span>'
            f'<code>{html.escape(name)}</code><span class="hex">{html.escape(value)}</span></li>')
    return ('<ul class="swatches">' + "".join(rows) + "</ul>"
            '<style>'
            '.swatches { list-style: none; margin: 12px 0 0; padding: 0;'
            ' display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 6px; }'
            '.swatches li { display: flex; align-items: center; gap: 8px; font-size: 12px; }'
            '.chip { width: 18px; height: 18px; border-radius: 4px;'
            ' border: 1px solid rgba(0,0,0,.2); flex: 0 0 auto; }'
            '.swatches .hex { margin-left: auto; opacity: .6; font-family: ui-monospace, monospace; }'
            '.swatches code { font-family: ui-monospace, monospace; }'
            '</style>')


def _contrast_table(derived: dict) -> str:
    rows = []
    for name, ratio in sorted(derived["contrast"].items(), key=lambda item: item[1]):
        state = "pass" if ratio >= derived["floor"] else "fail"
        rows.append(f'<tr class="{state}"><td><code>{html.escape(name)}</code></td>'
                    f"<td>{ratio}:1</td></tr>")
    corrections = ""
    if derived["adjustments"]:
        items = "".join(
            f'<li><code>{html.escape(entry["variable"])}</code> moved from '
            f'{html.escape(entry["from"])} to {html.escape(entry["to"])} to clear '
            f'{entry["floor"]}:1 on {html.escape(entry["against"])}</li>'
            for entry in derived["adjustments"])
        corrections = ("<p class=\"note\">Corrected on the way in, because a Panel is "
                       f"read from the back of a room:</p><ul>{items}</ul>")
    return (f'<table class="contrast"><thead><tr><th>Pairing</th><th>Ratio</th></tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table>{corrections}"
            '<style>'
            '.contrast { border-collapse: collapse; margin-top: 12px; font-size: 12px; }'
            '.contrast th, .contrast td { text-align: left; padding: 3px 14px 3px 0; }'
            '.contrast code { font-family: ui-monospace, monospace; }'
            '.contrast tr.fail td { color: #b00020; font-weight: 700; }'
            '.note { font-size: 12px; margin: 12px 0 4px; }'
            '</style>')


def _card(*, key: str, label: str, group: str, origin: str,
          variables: dict[str, str], derived: dict | None,
          source: dict | None, art_uris: dict[int, str] | None = None) -> str:
    """One design-system card: the mock, the palette, the numbers, the source."""
    embedded = ""
    if source is not None:
        payload = json.dumps(source, indent=2, ensure_ascii=False, sort_keys=True)
        embedded = (f'<script type="application/json" id="{SOURCE_BLOCK_ID}">'
                    f"{payload}</script>")
    provenance = {
        "yours": ("This theme round-trips. Edit the JSON below (or the colours in it), "
                  "and <code>tools/design_theme_studio.py import</code> writes it back "
                  "into the teacher's Library."),
        "built-in": ("Built in and reference only. Its CSS is hand-written in "
                     "<code>static/panels/themes.css</code>, so there is no authored "
                     "JSON to edit here. Copy the starter card to make something new."),
        "starter": ("A starting point. Change the colours in the JSON below, then import "
                    "it. Only <code>bg</code>, <code>ink</code>, <code>accent</code>, and "
                    "the optional <code>highlight</code> are yours to pick; everything "
                    "else is derived."),
    }[origin]
    numbers = _contrast_table(derived) if derived else (
        '<p class="note">Contrast for built-ins is verified in the Panels route card '
        "rather than derived here.</p>")
    return f"""<!-- @dsCard group="{group}" -->
<title>{html.escape(label)}</title>
<article class="card">
  <header>
    <h1>{html.escape(label)}</h1>
    <p class="meta"><code>?theme={html.escape(key)}</code> &middot; {origin}</p>
    <p class="meta">{provenance}</p>
  </header>
  {_mock_panel(variables, art_uris)}
  <section>
    <h2>Palette</h2>
    {_swatches(variables)}
  </section>
  <section>
    <h2>Contrast</h2>
    {numbers}
  </section>
  {f'<section><h2>Source</h2><pre class="source">{html.escape(json.dumps(source, indent=2, ensure_ascii=False, sort_keys=True))}</pre></section>' if source else ''}
  {embedded}
</article>
<style>
  .card {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
           line-height: 1.5; max-width: {CARD_WIDTH}px; }}
  .card h1 {{ font-size: 20px; margin: 0 0 2px; }}
  .card h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: .1em;
              margin: 22px 0 0; opacity: .7; }}
  .card .meta {{ font-size: 12px; margin: 0 0 6px; opacity: .75; }}
  .card code {{ font-family: ui-monospace, monospace; }}
  .card .source {{ font-size: 11px; background: rgba(127,127,127,.12);
                   padding: 10px; border-radius: 6px; overflow-x: auto; }}
  @media (prefers-color-scheme: dark) {{ .card {{ color: #e8e8e8; }} }}
</style>
"""


STARTER = {
    "version": panel_themes.VERSION,
    "key": "starter",
    "label": "Starter",
    "font": "sans",
    "ornament": "grid",
    "colors": {"bg": "#f8fafc", "ink": "#101c30", "accent": "#123a70",
               "highlight": "#c8102e"},
    "authored_by": "claude-design",
}


def _format_spec() -> str:
    fonts = "".join(f"<li><code>{key}</code>: {html.escape(value)}</li>"
                    for key, value in sorted(panel_themes.FONTS.items()))
    ornaments = "".join(f"<li><code>{name}</code></li>" for name in panel_themes.ORNAMENTS)
    art_extensions = ", ".join(f"<code>{ext}</code>" for ext in panel_themes.ART_EXTENSIONS)
    art_places = "".join(f"<li><code>{name}</code></li>"
                        for name in panel_themes.ART_PLACES)
    art_fields = "".join(f"<li><code>{name}</code></li>"
                        for name in sorted(panel_themes.ART_ENTRY_KEYS))
    art_recolors = ", ".join(f"<code>{name}</code>" for name in panel_themes.ART_RECOLORS)
    return f"""<!-- @dsCard group="Foundations" -->
<title>Panel theme format</title>
<article class="card">
  <h1>Panel theme format</h1>
  <p>A theme is a palette, a face, and one decorative layer. It cannot change
  layout: Panels measure their own body box to decide how many rows fit, so a
  theme that moved that box would change what a Panel shows rather than how it
  looks.</p>

  <h2>You pick four things</h2>
  <ul>
    <li><code>bg</code>: the page behind everything</li>
    <li><code>ink</code>: body text</li>
    <li><code>accent</code>: title, footer mark, row bars</li>
    <li><code>highlight</code> (optional): the emphasised row. Defaults to
    <code>accent</code>, so a second colour is what makes today stand out.</li>
  </ul>
  <p>Hex only, no alpha. Rows stay opaque so text always lands on flat colour
  even under a busy ornament.</p>

  <h2>Derived for you</h2>
  <p><code>--muted --rule --row --row-alt --pill-bg --pill-ink --today-bg
  --today-accent --today-ink --when-ink --warn-ink --title --ornament</code>,
  with every text pairing corrected to at least
  {panel_themes.CONTRAST_FLOOR}:1.</p>

  <h2>Faces</h2>
  <ul>{fonts}</ul>
  <p>Self-hosted or already on the machine. A theme may never name a font that
  would have to be fetched.</p>

  <h2>Ornaments</h2>
  <ul>{ornaments}</ul>
  <p>Built from your own colours as CSS gradients. No images, no network.</p>

  <h2>Art</h2>
  <p>A picture from a teacher's own file, placed by the code rather than drawn
  by it. Files live in <code>Library/Panels/Themes/art/</code>. Accepted
  types: {art_extensions}.</p>
  <p>Name a file after the theme's own key (<code>bobcats.svg</code> for the
  <code>bobcats</code> theme) and it attaches with no configuration at all:
  tucked in the bottom-right corner at a modest size, opacity
  {panel_themes.ART_DEFAULT_OPACITY}, recoloured to accent. To place more than
  one picture, or to change any of that, give the theme an <code>art</code>
  list, one entry per picture, with these fields:</p>
  <ul>{art_fields}</ul>
  <p><code>place</code> is one of: </p>
  <ul>{art_places}</ul>
  <p><code>recolor</code> is one of {art_recolors}, and only ever touches an
  SVG: a raster image (PNG, JPG, WEBP) keeps its own colours.</p>
  <p>Oversized files are handled automatically, the same way a font or an
  ornament never asks a teacher to think about it: a raster wider or taller
  than {panel_themes.ART_MAX_DIMENSION}px is downscaled, and every processed
  file is cached, so nobody has to think about file size or resolution before
  dropping a picture in.</p>

  <h2>Round trip</h2>
  <p>Each theme card embeds its authored JSON in a
  <code>&lt;script type="application/json" id="{SOURCE_BLOCK_ID}"&gt;</code>
  block. Edit that, then run
  <code>py tools/design_theme_studio.py import &lt;card.html&gt; --apply</code>
  to write it into <code>Library/Panels/Themes/</code>.</p>
</article>
<style>
  .card {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
           line-height: 1.6; max-width: 720px; }}
  .card h1 {{ font-size: 20px; margin: 0 0 8px; }}
  .card h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: .1em;
              margin: 22px 0 4px; opacity: .7; }}
  .card code {{ font-family: ui-monospace, monospace; }}
  @media (prefers-color-scheme: dark) {{ .card {{ color: #e8e8e8; }} }}
</style>
"""


def build() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []

    (OUT_DIR / "format.html").write_text(_format_spec(), encoding="utf-8")
    written.append("format.html")

    builtins = _builtin_variables()
    for key, label in panel_themes.BUILTIN_THEMES:
        variables = builtins.get(key, {})
        card = _card(key=key, label=label, group="Built in themes",
                     origin="built-in", variables=variables, derived=None,
                     source=None)
        (OUT_DIR / f"builtin-{key}.html").write_text(card, encoding="utf-8")
        written.append(f"builtin-{key}.html")

    starter_theme = panel_themes.normalize_theme(dict(STARTER, key="starter-copy-me",
                                                     label="Starter, copy me"))
    starter_derived = panel_themes.derive(starter_theme)
    (OUT_DIR / "starter.html").write_text(
        _card(key=starter_theme["key"], label=starter_theme["label"],
              group="Yours", origin="starter",
              variables=starter_derived["variables"], derived=starter_derived,
              source=starter_theme), encoding="utf-8")
    written.append("starter.html")

    loaded = panel_themes.load_custom_themes()
    for theme in loaded["themes"]:
        derived = panel_themes.derive(theme)
        art_uris = panel_themes._art_data_uris(theme)
        (OUT_DIR / f"yours-{theme['key']}.html").write_text(
            _card(key=theme["key"], label=theme["label"], group="Yours",
                  origin="yours", variables=derived["variables"],
                  derived=derived, source=theme, art_uris=art_uris),
            encoding="utf-8")
        written.append(f"yours-{theme['key']}.html")

    # A theme that got renamed or deleted leaves its old card sitting in the
    # output folder if nothing ever removes it, and a `yours-*.html` glob
    # pushed to the design project would then re-upload content that was
    # supposed to be gone. Only *.html at the top level is ours to prune;
    # anything else in the folder is left alone rather than assuming the
    # whole directory belongs to this script.
    stale = sorted(path.name for path in OUT_DIR.glob("*.html")
                   if path.name not in written)
    for name in stale:
        (OUT_DIR / name).unlink()

    print(f"bundle: {OUT_DIR}")
    for name in written:
        print(f"  {name}")
    if stale:
        print("removed stale cards:")
        for name in stale:
            print(f"  {name}")
    if loaded["problems"]:
        print("theme files skipped:")
        for problem in loaded["problems"]:
            print(f"  {problem['file']}: {problem['error']}")
    if not loaded["themes"]:
        print("no custom themes yet; the starter card is the one to copy")
    return 0


_SOURCE_RE = re.compile(
    r'<script[^>]*id=["\']' + SOURCE_BLOCK_ID + r'["\'][^>]*>(.*?)</script>',
    flags=re.S | re.I)


def extract_source(card_html: str) -> dict:
    """The authored theme embedded in a card, or a ValueError.

    Card HTML comes from a design project other people can edit, so it is data,
    not instruction: only this one JSON block is read, and it still has to pass
    the same validation as a hand-written file.
    """
    match = _SOURCE_RE.search(card_html)
    if not match:
        raise ValueError(
            f"no <script id=\"{SOURCE_BLOCK_ID}\"> block in this card. Built-in "
            "reference cards do not carry one; copy the starter card instead.")
    return json.loads(html.unescape(match.group(1)))


def import_card(path: str, *, apply: bool) -> int:
    card = Path(path).read_text(encoding="utf-8")
    try:
        raw = extract_source(card)
        theme = panel_themes.normalize_theme(raw)
        derived = panel_themes.derive(theme)
    except (ValueError, TypeError) as error:
        print(f"refused: {error}")
        return 1

    print(f"theme: {theme['key']} ({theme['label']})")
    print(f"font: {theme['font']}   ornament: {theme['ornament']}")
    print(f"colours: {json.dumps(theme['colors'], sort_keys=True)}")
    print(f"worst pairing: {derived['worst_pair']} at {derived['worst_ratio']}:1 "
          f"(floor {derived['floor']}:1)")
    for entry in derived["adjustments"]:
        print(f"  corrected {entry['variable']}: {entry['from']} -> {entry['to']}")

    if not apply:
        print("dry run. Pass --apply to write it into the workspace.")
        return 0

    root = workspace.workspace_root()
    if not root:
        print("refused: no workspace is configured on this machine.")
        return 1
    preview = panel_themes.build_preview(
        key=theme["key"], label=theme["label"], font=theme["font"],
        ornament=theme["ornament"], colors=theme["colors"],
        art=theme.get("art"), authored_by="claude-design")
    result = panel_themes.apply_preview(preview=preview,
                                        preview_digest_value=preview["digest"])
    verb = "replaced" if result["replaced"] else "wrote"
    print(f"{verb}: {result['path']}")
    print(f"available at ?theme={theme['key']}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build", help="write the Claude Design bundle to out/")
    importer = sub.add_parser("import", help="read a card back into a theme file")
    importer.add_argument("card", help="path to a card HTML file")
    importer.add_argument("--apply", action="store_true",
                          help="write it; without this the import is a dry run")
    args = parser.parse_args(argv)
    if args.command == "build":
        return build()
    return import_card(args.card, apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
