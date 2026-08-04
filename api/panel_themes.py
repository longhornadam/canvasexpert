"""Teacher-owned Panel themes: the authored file, the derived palette, the CSS.

A built-in theme is a hand-written block in ``static/panels/themes.css``. A
custom theme is a small JSON file the teacher keeps in their synced workspace
(``Library/Panels/Themes/<key>.json``) that this module turns into the same
kind of block at request time.

Three properties make it safe to hand that file to an assistant, or to a
teacher with a hex code and an opinion:

* **The generator emits, it never forwards.** Every value in the output is
  re-serialized from integers this module parsed itself, and the only selector
  it can produce is ``html[data-panel-theme="<key>"]`` plus that theme's
  ornament layer. A theme file therefore cannot set a box property on a kit
  element (which would change how many rows a Panel shows, see the sizing
  model in ``panel.css``), cannot smuggle CSS through a colour value, and
  cannot reach the network for a font or an image. Panels render unattended on
  a projector; a theme is not a place where a fetch may appear.

* **Fonts and ornaments are closed sets.** The teacher picks a face by name
  from ``FONTS``, which maps to a self-hosted or system stack, and a decoration
  by name from ``ORNAMENTS``, which this module builds out of their own
  colours. Neither is free text.

* **Contrast is corrected, not trusted.** A Panel is read from the back of a
  room, so every text-on-background pairing has to clear ``CONTRAST_FLOOR``.
  The teacher supplies three or four colours and this module derives the other
  twenty, darkening or lightening any text colour that falls short and
  reporting what it moved. An assistant picking pretty hex codes cannot
  produce an illegible wall.

The authored file is deliberately small. Everything a Panel actually consumes
is derived here, because the derivation is where the legibility rules live.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from api import operational_log, runtime_paths
from api.webui import workspace


VERSION = 1

# The built-in themes: the allowlist and the console's dropdown order. The
# rule blocks themselves are hand-written in ``static/panels/themes.css``; this
# is the one list of which keys exist, kept here rather than in the Panels
# route so the MCP tools can read it without importing a web route. The Panels
# route re-exports it as ``PANEL_THEMES``.
BUILTIN_THEMES = (
    ("ce", "Canvas Expert"),
    ("natural", "Natural"),
    ("ocean", "Ocean"),
    ("cottage", "Cottage"),
    ("console", "Console"),
    ("wizardtrain", "Wizard train"),
    ("bauhaus", "Bauhaus"),
    ("lisa", "Lisa"),
)
BUILTIN_KEYS = frozenset(key for key, _label in BUILTIN_THEMES)

# The authored shape. Anything else in the file is rejected rather than
# ignored, so a typo in a key name is visible instead of silently doing
# nothing to the wall.
ROOT_KEYS = {"version", "key", "label", "font", "ornament", "colors", "art",
             "authored_at", "authored_by"}
REQUIRED_COLORS = ("bg", "ink", "accent")
OPTIONAL_COLORS = ("highlight",)
COLOR_SLOTS = REQUIRED_COLORS + OPTIONAL_COLORS

# Theme art: a teacher drops a picture into Library/Panels/Themes/art/ and it
# becomes the theme's decoration. The teacher never thinks about size, format,
# or resolution; the code absorbs every limit silently.
ART_EXTENSIONS = (".svg", ".png", ".jpg", ".jpeg", ".webp")
ART_PLACES = ("corner-tl", "corner-tr", "corner-bl", "corner-br", "scatter",
              "tile", "band-bottom", "watermark", "cover")
ART_RECOLORS = ("accent", "ink", "highlight", "bg", "none")
ART_MIN_SIZE = 4
ART_MAX_SIZE = 80
ART_MIN_OPACITY = 0.05
ART_MAX_OPACITY = 1.0
ART_DEFAULT_OPACITY = 0.5
ART_MAX_DIMENSION = 1600
ART_CACHE_DIR = "panel-art-cache"
# The scrim that keeps the title and footer readable over a full-bleed photo.
ART_COVER_SCRIM_ALPHA = 0.55

# Faces that are already on the machine: self-hosted in /static/fonts or a
# system face everywhere this ships. A theme must never name a font the
# machine would have to fetch.
FONTS = {
    "sans": "'Public Sans', 'Segoe UI', system-ui, sans-serif",
    "grotesk": "'Schibsted Grotesk', 'Public Sans', system-ui, sans-serif",
    "serif": "Georgia, 'Iowan Old Style', 'Times New Roman', serif",
    "mono": "'JetBrains Mono', ui-monospace, Consolas, monospace",
}
DEFAULT_FONT = "sans"

ORNAMENTS = ("none", "grid", "scanlines", "hatch", "dots", "glow", "seams",
             "frame")
DEFAULT_ORNAMENT = "grid"

KEY_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")
HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")

MAX_LABEL_LENGTH = 40
CONTRAST_FLOOR = 4.5
# Ornament and row bars are decoration rather than words, so they answer to a
# visibility floor instead of the reading floor.
DECOR_FLOOR = 3.0

_STORE_LOCK = threading.RLock()


class ThemeError(ValueError):
    """The authored theme is not usable as written."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


# ── colour ────────────────────────────────────────────────────────────────
# Small and self-contained on purpose: the contrast maths is the part that
# keeps an AI-authored palette readable, so it should not depend on anything
# that could be absent on a district machine.

def parse_hex(value, label: str) -> tuple[int, int, int]:
    """A 3- or 6-digit hex colour as integers, or a ThemeError.

    Hex only. Named colours would open the door to arbitrary CSS keywords,
    and alpha would let a row go translucent, which is what keeps row text on
    flat colour when a busy ornament sits underneath.
    """
    text = "" if value is None else str(value).strip()
    if not HEX_RE.match(text):
        raise ThemeError(
            f"{label} must be a hex colour like #123a70, got {text!r}")
    digits = text[1:]
    if len(digits) == 3:
        digits = "".join(char * 2 for char in digits)
    return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))


def to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def _channel_luminance(channel: int) -> float:
    ratio = channel / 255
    if ratio <= 0.04045:
        return ratio / 12.92
    return ((ratio + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[int, int, int]) -> float:
    red, green, blue = (_channel_luminance(c) for c in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def mix(first: tuple[int, int, int], second: tuple[int, int, int],
        amount: float) -> tuple[int, int, int]:
    """``amount`` of ``second`` blended into ``first``."""
    amount = max(0.0, min(1.0, amount))
    return tuple(int(round(a + (b - a) * amount))
                 for a, b in zip(first, second))


def toward_contrast(foreground: tuple[int, int, int],
                    background: tuple[int, int, int],
                    target: float) -> tuple[tuple[int, int, int], bool]:
    """Push a text colour away from its background until it clears ``target``.

    Moves toward whichever of black or white gains contrast, so a chosen
    accent keeps its hue as long as possible and only loses lightness. One of
    the two extremes always clears 4.5:1 against any background, so this
    cannot fail at the reading floor.
    """
    if contrast(foreground, background) >= target:
        return foreground, False
    black, white = (0, 0, 0), (255, 255, 255)
    goal = black if contrast(black, background) >= contrast(white, background) else white
    candidate = foreground
    for step in range(1, 101):
        candidate = mix(foreground, goal, step / 100)
        if contrast(candidate, background) >= target:
            return candidate, True
    return candidate, True


def _worst(colour: tuple[int, int, int],
           backgrounds: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    """The background this colour reads worst against."""
    return min(backgrounds, key=lambda background: contrast(colour, background))


def _reachable_ceiling(backgrounds: list[tuple[int, int, int]]) -> float:
    """The best any single ink could do against every one of these beds at
    once: whichever of pure black or pure white has the higher worst-case
    contrast across all of them.

    Rows are lifted away from the page (see the comment on the lift in
    ``derive()``) so that ``--row`` and ``--row-alt`` never collapse into
    ``--bg`` on a near-white page. That same lift is what spreads the three
    text beds far enough apart, on some mid-tone pages, that black clears the
    floor on the lightest bed but not the darkest, and white does the
    opposite: no single ink can then clear the floor against all three, no
    matter how it is chosen. That is a hard ceiling below ``CONTRAST_FLOOR``
    for a small slice of possible backgrounds, not a bug, and shrinking the
    lift to avoid it would reintroduce the near-white banding it was added to
    fix. Reporting the ceiling honestly is the correct response, not chasing
    it by touching the lift.
    """
    black, white = (0, 0, 0), (255, 255, 255)
    best_black = min(contrast(black, bed) for bed in backgrounds)
    best_white = min(contrast(white, bed) for bed in backgrounds)
    return max(best_black, best_white)


def toward_contrast_all(foreground, backgrounds, target):
    """Push a text colour until it clears ``target`` against EVERY bed it can
    land on.

    Correcting against only the worst bed is not enough: moving the colour
    reorders which bed is worst, so a colour aimed at one bed can stop just
    short on another. Rows usually sit close enough to the page that all
    three beds are on the same side of the text and one direction raises
    contrast against all of them at once.

    On some mid-tone pages the beds spread far enough apart (the row lift in
    ``derive()``) that black and white each fall short on a different bed, and
    the choice of which extreme to chase has to be made on the beds
    themselves, not on the original colour: comparing black and white by
    their own worst-case contrast across every bed picks whichever one is
    truly less bad. Choosing by the original colour's own worst bed instead
    can send two different starting colours toward two different goals on the
    very same page, so one of them lands short of what the other reaches.
    """
    beds = list(backgrounds)
    if all(contrast(foreground, bed) >= target for bed in beds):
        return foreground, False
    black, white = (0, 0, 0), (255, 255, 255)
    best_black = min(contrast(black, bed) for bed in beds)
    best_white = min(contrast(white, bed) for bed in beds)
    goal = black if best_black >= best_white else white
    candidate = foreground
    for step in range(1, 101):
        candidate = mix(foreground, goal, step / 100)
        if all(contrast(candidate, bed) >= target for bed in beds):
            return candidate, True
    return candidate, True


# ── the authored file ─────────────────────────────────────────────────────

def _normalize_label(value) -> str:
    text = "" if value is None else str(value)
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise ThemeError("label contains control characters")
    if "<" in text or ">" in text:
        raise ThemeError("label must be plain text")
    text = " ".join(text.split())
    if not text:
        raise ThemeError("label is required")
    if len(text) > MAX_LABEL_LENGTH:
        raise ThemeError(f"label must be {MAX_LABEL_LENGTH} characters or fewer")
    return text


def normalize_key(value) -> str:
    text = "" if value is None else str(value).strip().lower()
    if not KEY_RE.match(text):
        raise ThemeError(
            "key must be 1 to 32 characters of lowercase letters, digits, and "
            f"inner hyphens, got {text!r}")
    return text


def normalize_theme(raw, *, builtin_keys=BUILTIN_KEYS) -> dict:
    """Validate an authored theme into its canonical stored form."""
    if not isinstance(raw, dict):
        raise ThemeError("a theme must be a JSON object")
    unknown = set(raw) - ROOT_KEYS
    if unknown:
        raise ThemeError("unknown field(s): " + ", ".join(sorted(unknown)))
    version = raw.get("version", VERSION)
    if version != VERSION:
        raise ThemeError(f"unsupported theme version {version!r}")

    key = normalize_key(raw.get("key"))
    if key in builtin_keys:
        raise ThemeError(
            f"{key!r} is a built-in theme. Pick a different key so the "
            "built-in stays available.")

    font = str(raw.get("font") or DEFAULT_FONT).strip().lower()
    if font not in FONTS:
        raise ThemeError("font must be one of: " + ", ".join(sorted(FONTS)))
    ornament = str(raw.get("ornament") or DEFAULT_ORNAMENT).strip().lower()
    if ornament not in ORNAMENTS:
        raise ThemeError("ornament must be one of: " + ", ".join(ORNAMENTS))

    colors = raw.get("colors")
    if not isinstance(colors, dict):
        raise ThemeError("colors must be an object with " +
                         ", ".join(REQUIRED_COLORS))
    unknown_colors = set(colors) - set(COLOR_SLOTS)
    if unknown_colors:
        raise ThemeError("unknown colour(s): " + ", ".join(sorted(unknown_colors)))
    stored_colors = {}
    for slot in REQUIRED_COLORS:
        if slot not in colors:
            raise ThemeError(f"colors.{slot} is required")
        stored_colors[slot] = to_hex(parse_hex(colors[slot], f"colors.{slot}"))
    for slot in OPTIONAL_COLORS:
        if colors.get(slot) is not None:
            stored_colors[slot] = to_hex(parse_hex(colors[slot], f"colors.{slot}"))

    stored_art = _normalize_art(raw.get("art"))

    theme = {
        "version": VERSION,
        "key": key,
        "label": _normalize_label(raw.get("label")),
        "font": font,
        "ornament": ornament,
        "colors": stored_colors,
        "authored_at": str(raw.get("authored_at") or _now()),
        "authored_by": str(raw.get("authored_by") or "assistant")[:40],
    }
    if stored_art:
        theme["art"] = stored_art
    return theme


ART_ENTRY_KEYS = {"file", "place", "size", "opacity", "recolor"}


def _normalize_art(raw) -> list[dict]:
    """Validate the optional ``art`` list into its canonical stored form.

    ``file`` is a filename only: anything with a separator or ``..`` is refused
    so an entry can never escape the art folder. ``place``, ``size``,
    ``opacity``, and ``recolor`` are clamped to their closed sets. A missing or
    empty list is fine; a malformed entry is refused rather than ignored.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ThemeError("art must be a list of entries")
    stored = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ThemeError(f"art[{index}] must be an object")
        unknown = set(entry) - ART_ENTRY_KEYS
        if unknown:
            raise ThemeError("unknown art field(s): " + ", ".join(sorted(unknown)))
        filename = str(entry.get("file") or "").strip()
        if not filename:
            raise ThemeError(f"art[{index}].file is required")
        if "/" in filename or "\\" in filename or ".." in filename:
            raise ThemeError(
                f"art[{index}].file must be a filename only, got {filename!r}")
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ART_EXTENSIONS:
            raise ThemeError(
                f"art[{index}].file must end in one of "
                + ", ".join(ART_EXTENSIONS) + f", got {filename!r}")
        place = str(entry.get("place") or "corner-br").strip().lower()
        if place not in ART_PLACES:
            raise ThemeError("art place must be one of: " + ", ".join(ART_PLACES))
        size = entry.get("size")
        if size is None:
            size = 22
        try:
            size = float(size)
        except (TypeError, ValueError):
            raise ThemeError(f"art[{index}].size must be a number")
        size = max(ART_MIN_SIZE, min(ART_MAX_SIZE, size))
        opacity = entry.get("opacity")
        if opacity is None:
            opacity = ART_DEFAULT_OPACITY
        try:
            opacity = float(opacity)
        except (TypeError, ValueError):
            raise ThemeError(f"art[{index}].opacity must be a number")
        opacity = max(ART_MIN_OPACITY, min(ART_MAX_OPACITY, opacity))
        recolor = str(entry.get("recolor") or "accent").strip().lower()
        if recolor not in ART_RECOLORS:
            raise ThemeError("art recolor must be one of: " + ", ".join(ART_RECOLORS))
        stored.append({
            "file": filename,
            "place": place,
            "size": size,
            "opacity": opacity,
            "recolor": recolor,
        })
    return stored


# ── derivation ────────────────────────────────────────────────────────────

def derive(theme: dict) -> dict:
    """Turn three or four authored colours into the full variable set.

    The backgrounds are settled first, then every text colour is corrected
    against the worst background it can land on. ``--row`` and ``--row-alt``
    stay near ``--bg`` on purpose: they are the opaque bed row text sits on,
    and a big jump there would fight the ornament showing through the gutters.
    """
    colors = theme["colors"]
    bg = parse_hex(colors["bg"], "colors.bg")
    ink_raw = parse_hex(colors["ink"], "colors.ink")
    accent_raw = parse_hex(colors["accent"], "colors.accent")
    highlight_raw = (parse_hex(colors["highlight"], "colors.highlight")
                     if colors.get("highlight") else accent_raw)

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

    pill_bg = mix(bg, accent_raw, 0.18)
    today_bg = mix(bg, highlight_raw, 0.20)
    text_beds = [bg, row, row_alt]

    adjustments = []

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

    ink = corrected("--ink", ink_raw, text_beds)
    muted = corrected("--muted", mix(ink, bg, 0.35), text_beds)
    title = corrected("--title", accent_raw, [bg])
    accent = corrected("--accent", accent_raw, [bg])
    pill_ink = corrected("--pill-ink", accent_raw, [pill_bg])
    today_ink = corrected("--today-ink", highlight_raw, [today_bg])
    today_accent = corrected("--today-accent", highlight_raw, [bg], DECOR_FLOOR)
    warn_ink = corrected("--warn-ink", highlight_raw, text_beds)

    variables = {
        "--panel-font": FONTS[theme["font"]],
        "--bg": to_hex(bg),
        "--ink": to_hex(ink),
        "--title": to_hex(title),
        "--muted": to_hex(muted),
        "--rule": to_hex(mix(bg, ink, 0.32)),
        "--accent": to_hex(accent),
        "--row": to_hex(row),
        "--row-alt": to_hex(row_alt),
        "--pill-bg": to_hex(pill_bg),
        "--pill-ink": to_hex(pill_ink),
        "--today-bg": to_hex(today_bg),
        "--today-accent": to_hex(today_accent),
        "--today-ink": to_hex(today_ink),
        "--when-ink": to_hex(muted),
        "--warn-ink": to_hex(warn_ink),
    }
    ornament_layers, ornament_opacity = _ornament(
        theme["ornament"], bg=bg, ink=ink_raw, accent=accent_raw,
        highlight=highlight_raw)
    art_layers, art_diagnostics, art_info = _art_layers(
        theme, bg=bg, ink=ink, accent=accent, highlight=highlight_raw)
    # Art layers come first so they sit above the gradient recipe, which is
    # how the built-in themes compose their leaves over a radial gradient.
    layers = art_layers + ornament_layers
    if layers:
        variables["--ornament"] = ", ".join(layers)
        variables["--ornament-opacity"] = ornament_opacity

    pairs = [
        ("--ink on --row", ink, row), ("--ink on --row-alt", ink, row_alt),
        ("--ink on --bg", ink, bg), ("--muted on --row", muted, row),
        ("--muted on --bg", muted, bg), ("--title on --bg", title, bg),
        ("--accent on --bg", accent, bg),
        ("--pill-ink on --pill-bg", pill_ink, pill_bg),
        ("--today-ink on --today-bg", today_ink, today_bg),
        ("--warn-ink on --row", warn_ink, row),
    ]
    measured = {name: round(contrast(fore, back), 2) for name, fore, back in pairs}
    # Some page colours have no ink that clears the floor against all three
    # text beds at once (see _reachable_ceiling); report that honestly rather
    # than silently landing short of the advertised floor.
    ceiling = _reachable_ceiling(text_beds)
    result = {
        "variables": variables,
        "contrast": measured,
        "floor": CONTRAST_FLOOR,
        "adjustments": adjustments,
        "worst_pair": min(measured, key=measured.get),
        "worst_ratio": min(measured.values()),
        "floor_reachable": ceiling >= CONTRAST_FLOOR,
        "floor_ceiling": round(ceiling, 2),
    }
    if art_diagnostics:
        result["art_diagnostics"] = art_diagnostics
    if art_info:
        result["art"] = art_info
    return result


def _art_layers(theme, *, bg, ink, accent, highlight) -> tuple[list[str], list[dict], list[dict]]:
    """Compile a theme's art entries into background layers.

    Returns (layers, diagnostics, info). A missing or unreadable file degrades
    to the gradient ornament with a named diagnostic; it never loses the theme.
    ``cover`` entries add a scrim layer on top so the title and footer stay
    readable over a full-bleed photo.
    """
    entries = theme.get("art") or []
    if not entries:
        return [], [], []
    derived_colors = {
        "bg": to_hex(bg),
        "ink": to_hex(ink),
        "accent": to_hex(accent),
        "highlight": to_hex(highlight),
    }
    layers, diagnostics, info = [], [], []
    has_cover = any(entry["place"] == "cover" for entry in entries)
    if has_cover:
        scrim = f"linear-gradient({_rgba(bg, ART_COVER_SCRIM_ALPHA)}, {_rgba(bg, ART_COVER_SCRIM_ALPHA)})"
        layers.append(scrim)
    for index, entry in enumerate(entries):
        source = _art_source_path(entry["file"])
        if not source or not os.path.isfile(workspace.extended_path(source)):
            diagnostics.append({
                "file": entry["file"],
                "error": f"{entry['file']} is not in the art folder.",
            })
            continue
        data, ext, diagnostic = _process_art(source, entry, derived_colors)
        if diagnostic:
            diagnostics.append({"file": entry["file"], "error": diagnostic})
        if not data:
            continue
        content_hash = hashlib.sha256(data).hexdigest()
        url = _art_url(theme["key"], index, ext, content_hash)
        placement = _placement_layers(entry, entry["size"])
        for layer in placement:
            layers.append(f'url("{url}") {layer}')
        info.append({
            "file": entry["file"],
            "place": entry["place"],
            "size": entry["size"],
            "opacity": entry["opacity"],
            "recolor": entry["recolor"],
            "url": url,
            "bytes": len(data),
        })
    return layers, diagnostics, info


def _art_data_uris(theme: dict) -> dict[int, str]:
    """Processed art bytes as data URIs, keyed by entry index.

    The design studio inlines these into cards because the card is pushed to a
    claude.ai/design project where the local ``/panels/theme-art/...`` route
    does not resolve. The app itself uses the route; only the cards inline.
    """
    entries = theme.get("art") or []
    uris = {}
    derived = derive(theme)
    derived_colors = {
        "bg": derived["variables"]["--bg"],
        "ink": derived["variables"]["--ink"],
        "accent": derived["variables"]["--accent"],
        "highlight": derived["variables"]["--today-accent"],
    }
    for index, entry in enumerate(entries):
        source = _art_source_path(entry["file"])
        if not source or not os.path.isfile(workspace.extended_path(source)):
            continue
        data, ext, _diagnostic = _process_art(source, entry, derived_colors)
        if not data:
            continue
        media = {
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(ext, "application/octet-stream")
        import base64
        uris[index] = f"data:{media};base64,{base64.b64encode(data).decode('ascii')}"
    return uris


def _synthesize_zero_config_art(theme: dict, root=None) -> list[dict]:
    """If a theme has no art but ``art/<key>.<ext>`` exists, attach it.

    Dropping a file named after your theme is then the entire setup: one entry,
    corner-bottom-right, 22vmin, 0.5 opacity, recoloured to accent.
    """
    if theme.get("art"):
        return theme["art"]
    directory = art_dir(root)
    if not directory or not os.path.isdir(workspace.extended_path(directory)):
        return []
    key = theme["key"]
    try:
        names = os.listdir(workspace.extended_path(directory))
    except OSError:
        return []
    for name in names:
        stem, ext = os.path.splitext(name)
        if stem == key and ext.lower() in ART_EXTENSIONS:
            return [{
                "file": name,
                "place": "corner-br",
                "size": 22,
                "opacity": ART_DEFAULT_OPACITY,
                "recolor": "accent",
            }]
    return []


def list_theme_art(*, root=None) -> dict:
    """The art files present, their kind, dimensions or viewBox, and any
    diagnostic. The assistant references filenames that exist instead of
    inventing them."""
    directory = art_dir(root)
    files, problems = [], []
    if not directory or not os.path.isdir(workspace.extended_path(directory)):
        return {"files": files, "problems": problems}
    try:
        names = sorted(name for name in os.listdir(workspace.extended_path(directory))
                       if os.path.splitext(name)[1].lower() in ART_EXTENSIONS)
    except OSError as error:
        return {"files": files, "problems": [{"file": directory, "error": str(error)}]}
    for name in names:
        path = os.path.join(directory, name)
        ext = os.path.splitext(name)[1].lower()
        entry = {"file": name, "kind": ext.lstrip(".")}
        if ext == ".svg":
            try:
                with open(workspace.extended_path(path), "rb") as handle:
                    root_el = ET.fromstring(handle.read())
                entry["viewBox"] = root_el.get("viewBox")
                if not entry["viewBox"]:
                    problems.append({"file": name, "error":
                        f"{name} has no size information, so it cannot scale to a projector."})
            except (ET.ParseError, OSError):
                problems.append({"file": name, "error": f"Could not read {name}."})
        else:
            try:
                from PIL import Image
                with Image.open(workspace.extended_path(path)) as image:
                    entry["width"], entry["height"] = image.size
            except Exception:
                problems.append({"file": name, "error": f"Could not read {name}."})
        files.append(entry)
    return {"files": files, "problems": problems}


def _rgba(rgb: tuple[int, int, int], alpha: float) -> str:
    red, green, blue = (max(0, min(255, int(round(c)))) for c in rgb)
    return f"rgba({red}, {green}, {blue}, {round(max(0.0, min(1.0, alpha)), 3)})"


def _ornament(name: str, *, bg, ink, accent, highlight) -> tuple[list[str], float]:
    """One decorative layer, built from the theme's own colours.

    Every recipe is CSS gradients only. No ``url()``, so a theme can never put
    a network fetch behind a Panel that has to survive a whole period on a
    classroom wall, and no per-element rules, so ornament cannot touch layout.
    """
    if name == "none":
        return [], 0.0
    if name == "grid":
        line = _rgba(ink, 0.05)
        return ([f"repeating-linear-gradient(0deg, {line} 0 1px, transparent 1px 4vmin)",
                 f"repeating-linear-gradient(90deg, {line} 0 1px, transparent 1px 4vmin)"], 1.0)
    if name == "scanlines":
        return ([f"repeating-linear-gradient(0deg, {_rgba(ink, 0.10)} 0 2px, transparent 2px 4px)",
                 f"radial-gradient(110% 80% at 50% 0%, {_rgba(accent, 0.10)}, transparent 60%)"], 0.85)
    if name == "hatch":
        return ([f"repeating-linear-gradient(45deg, {_rgba(accent, 0.07)} 0 2px, transparent 2px 7px)",
                 f"repeating-linear-gradient(-45deg, {_rgba(highlight, 0.06)} 0 2px, transparent 2px 7px)"], 0.9)
    if name == "dots":
        return ([f"radial-gradient(circle, {_rgba(accent, 0.16)} 0 0.35vmin, transparent 0.35vmin) 0 0 / 4vmin 4vmin",
                 f"radial-gradient(120% 80% at 50% 100%, {_rgba(accent, 0.10)}, transparent 70%)"], 0.8)
    if name == "glow":
        return ([f"radial-gradient(90% 60% at 12% 0%, {_rgba(accent, 0.26)}, transparent 62%)",
                 f"radial-gradient(90% 60% at 88% 100%, {_rgba(highlight, 0.22)}, transparent 62%)"], 0.8)
    if name == "seams":
        return ([f"repeating-linear-gradient(90deg, {_rgba(ink, 0.22)} 0 1px, transparent 1px 2.2vmin)",
                 f"linear-gradient(180deg, {_rgba(accent, 0.22)} 0 0.5vmin, transparent 0.5vmin)",
                 f"linear-gradient(0deg, {_rgba(accent, 0.22)} 0 0.5vmin, transparent 0.5vmin)"], 0.9)
    if name == "frame":
        edge = _rgba(accent, 0.5)
        inner = _rgba(highlight, 0.28)
        return ([f"linear-gradient({edge}, {edge}) no-repeat left 1.2vmin top 1.2vmin / calc(100% - 2.4vmin) 0.45vmin",
                 f"linear-gradient({edge}, {edge}) no-repeat left 1.2vmin bottom 1.2vmin / calc(100% - 2.4vmin) 0.45vmin",
                 f"linear-gradient({edge}, {edge}) no-repeat left 1.2vmin top 1.2vmin / 0.45vmin calc(100% - 2.4vmin)",
                 f"linear-gradient({edge}, {edge}) no-repeat right 1.2vmin top 1.2vmin / 0.45vmin calc(100% - 2.4vmin)",
                 f"linear-gradient(160deg, {inner}, transparent 55%)"], 0.9)
    return [], 0.0


def resolved(theme: dict) -> dict:
    """The stored theme plus everything a Panel needs to render it."""
    return {"theme": copy.deepcopy(theme), **derive(theme)}


# ── CSS ───────────────────────────────────────────────────────────────────

def theme_css(theme: dict) -> str:
    """One rule block for one custom theme.

    The only selector this can produce is the theme's own attribute selector.
    That is what makes the sizing model safe by construction rather than by
    review: there is no code path here that emits a kit class.
    """
    variables = derive(theme)["variables"]
    lines = [f'html[data-panel-theme="{theme["key"]}"] {{']
    for name in sorted(variables):
        value = variables[name]
        lines.append(f"  {name}: {value};")
    lines.append("}")
    return "\n".join(lines)


def custom_css(themes) -> str:
    """The stylesheet for every valid custom theme, in load order."""
    header = ("/* Generated from Library/Panels/Themes. Do not edit: edit the\n"
              "   theme files, or ask your assistant to. */\n")
    blocks = [theme_css(theme) for theme in themes]
    if not blocks:
        return header + "/* No custom themes yet. */\n"
    return header + "\n\n".join(blocks) + "\n"


# ── storage ───────────────────────────────────────────────────────────────

def theme_path(key: str, root=None):
    directory = workspace.panel_themes_dir(root)
    return os.path.join(directory, f"{normalize_key(key)}.json") if directory else None


def art_dir(root=None):
    """Where the teacher's art files live, one per theme or named by entry."""
    directory = workspace.panel_themes_dir(root)
    return os.path.join(directory, "art") if directory else None


def art_cache_dir():
    """Machine-local cache of processed art bytes.

    Deliberately NOT in the synced workspace: derived bytes in a synced folder
    would churn OneDrive for no reason. Keyed on source + entry so a change to
    opacity, recolor, or place rebuilds.
    """
    return runtime_paths.local_app_dir() / ART_CACHE_DIR


def _art_source_path(filename: str, root=None):
    directory = art_dir(root)
    if not directory:
        return None
    return os.path.join(directory, filename)


def _art_cache_key(source_path, mtime, size, entry) -> str:
    """The cache key for one processed art entry.

    The output depends on the source bytes and on the entry's opacity, recolor,
    and place (place affects downscale target), so all of them go in.
    """
    raw = json.dumps({
        "source": str(source_path),
        "mtime": mtime,
        "size": size,
        "opacity": entry["opacity"],
        "recolor": entry["recolor"],
        "place": entry["place"],
    }, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _art_cache_path(key: str, ext: str) -> str:
    return str(art_cache_dir() / f"{key}{ext}")


# ── art placement ─────────────────────────────────────────────────────────

def _placement_layers(entry: dict, size: float) -> list[str]:
    """The background shorthand layers for one art entry's placement.

    ``size`` is the entry's size in vmin, already clamped. ``cover`` is handled
    separately (it needs the scrim), so it returns a single ``cover`` layer.
    """
    place = entry["place"]
    if place == "corner-tl":
        return [f"no-repeat left -2vmin top -3vmin / {size}vmin"]
    if place == "corner-tr":
        return [f"no-repeat right -2vmin top -3vmin / {size}vmin"]
    if place == "corner-bl":
        return [f"no-repeat left -2vmin bottom -3vmin / {size}vmin"]
    if place == "corner-br":
        return [f"no-repeat right -2vmin bottom -3vmin / {size}vmin"]
    if place == "scatter":
        return [
            f"no-repeat left 6% top 9% / {size}vmin",
            f"no-repeat right 8% top 38% / {size * 0.7}vmin",
            f"no-repeat left 22% bottom 11% / {size * 0.85}vmin",
        ]
    if place == "tile":
        return [f"repeat 0 0 / {size}vmin {size}vmin"]
    if place == "band-bottom":
        return [f"repeat-x left bottom / auto {size}vmin"]
    if place == "watermark":
        return [f"no-repeat center / {size}vmin"]
    if place == "cover":
        return [f"no-repeat center / cover"]
    return [f"no-repeat right -2vmin bottom -3vmin / {size}vmin"]


def _art_url(key: str, index: int, ext: str, content_hash: str) -> str:
    """The hashed, immutable URL the generated CSS references."""
    return f"/panels/theme-art/{key}/{index}{ext}?v={content_hash}"


# ── art ingest ────────────────────────────────────────────────────────────

# Namespaces an editor writes that carry no rendering meaning. Dropping them
# (and their attributes) is the bulk of an Illustrator export's size.
_EDITOR_NS = {
    "http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd": "sodipodi",
    "http://www.inkscape.org/namespaces/inkscape": "inkscape",
}
_EDITOR_NS_URIS = frozenset(_EDITOR_NS)
# Attributes in these namespaces are editor cruft too.
_EDITOR_ATTR_NS = ("sodipodi", "inkscape")

# Numeric attributes that carry geometry and can be rounded to 2 decimals.
_NUMERIC_ATTRS = {
    "x", "y", "cx", "cy", "r", "rx", "ry", "width", "height", "x1", "y1",
    "x2", "y2", "d", "points", "offset", "stdDeviation", "fx", "fy",
}


def _round_svg_numbers(text: str) -> str:
    """Round every numeric literal in an SVG attribute value to 2 decimals."""
    def repl(match):
        value = float(match.group(0))
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return re.sub(r"-?\d+\.\d+", repl, text)


def _parent_of(root: ET.Element, child: ET.Element):
    """The parent of ``child`` in the tree rooted at ``root``, or None."""
    for parent in root.iter():
        if child in list(parent):
            return parent
    return None


def _strip_editor_cruft(root: ET.Element) -> None:
    """Remove editor namespaces, metadata, and comments from a parsed SVG."""
    for uri in _EDITOR_NS_URIS:
        for element in root.iter():
            for attr in list(element.attrib):
                if attr.startswith(f"{{{uri}}}"):
                    del element.attrib[attr]
    # Remove metadata elements wherever they sit (their tag is namespaced, so
    # compare the local name).
    for element in list(root.iter()):
        if element.tag.rsplit("}", 1)[-1] == "metadata":
            parent = _parent_of(root, element)
            if parent is not None:
                parent.remove(element)
    # Remove comments (they are not elements in ElementTree, so handled at
    # serialization time by dropping them from the tree walk).


def _recolor_svg(root: ET.Element, hex_colour: str) -> None:
    """Replace every fill/stroke that is not ``none`` with the palette hex."""
    for element in root.iter():
        for attr in ("fill", "stroke"):
            value = element.get(attr)
            if value is not None and value.strip().lower() != "none":
                element.set(attr, hex_colour)


def _process_svg(source_path, entry, derived_colors) -> tuple[bytes, str, str]:
    """Parse, clean, recolor, and re-serialize an SVG.

    Returns (bytes, extension, diagnostic). The diagnostic is None when the art
    is usable; otherwise it is a plain-sentence message with an obvious next
    step, and the caller still renders (degrading to the gradient ornament).
    """
    try:
        with open(source_path, "rb") as handle:
            raw = handle.read()
        root = ET.fromstring(raw)
    except (ET.ParseError, OSError) as error:
        return b"", ".svg", f"Could not read {os.path.basename(source_path)}."
    _strip_editor_cruft(root)
    # Round geometry numbers.
    for element in root.iter():
        for attr in list(element.attrib):
            if attr in _NUMERIC_ATTRS:
                element.set(attr, _round_svg_numbers(element.get(attr)))
    viewbox = root.get("viewBox")
    if not viewbox:
        return b"", ".svg", (
            f"{os.path.basename(source_path)} has no size information, so it "
            "cannot scale to a projector.")
    if entry["recolor"] != "none":
        _recolor_svg(root, derived_colors[entry["recolor"]])
    # Bake opacity in by wrapping the document contents in a group.
    if entry["opacity"] < 1.0:
        children = list(root)
        group = ET.Element("g", {"opacity": f"{entry['opacity']:.2f}"})
        for child in children:
            root.remove(child)
            group.append(child)
        root.append(group)
    body = ET.tostring(root, encoding="unicode")
    return body.encode("utf-8"), ".svg", None


def _process_raster(source_path, entry) -> tuple[bytes, str, str]:
    """Downscale, apply alpha, and re-encode a raster image.

    Returns (bytes, extension, diagnostic). ``recolor`` does not apply to
    rasters and is silently ignored.
    """
    try:
        from PIL import Image
    except Exception:
        return b"", ".png", "Image support is not installed."
    try:
        with Image.open(source_path) as image:
            image.load()
            if image.mode not in ("RGBA", "LA"):
                image = image.convert("RGBA")
            width, height = image.size
            longest = max(width, height)
            if longest > ART_MAX_DIMENSION:
                scale = ART_MAX_DIMENSION / longest
                image = image.resize(
                    (max(1, int(width * scale)), max(1, int(height * scale))),
                    Image.LANCZOS)
            if entry["opacity"] < 1.0:
                alpha = image.getchannel("A").point(
                    lambda value: int(value * entry["opacity"]))
                image.putalpha(alpha)
            has_alpha = image.mode == "RGBA"
            if has_alpha:
                buffer = __import__("io").BytesIO()
                image.save(buffer, format="PNG")
                return buffer.getvalue(), ".png", None
            buffer = __import__("io").BytesIO()
            image.convert("RGB").save(buffer, format="JPEG", quality=85)
            return buffer.getvalue(), ".jpg", None
    except (OSError, ValueError) as error:
        return b"", ".png", f"Could not read {os.path.basename(source_path)}."


def _art_diagnostic(source_path, entry) -> str | None:
    """A plain-sentence diagnostic for art that will not look good.

    Never refuses: the theme still renders, degrading to its gradient ornament.
    """
    filename = os.path.basename(source_path)
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".svg":
        return None  # SVG diagnostics (viewBox, web image) are handled in _process_svg
    try:
        from PIL import Image
        with Image.open(source_path) as image:
            width, height = image.size
    except Exception:
        return f"Could not read {filename}."
    longest = max(width, height)
    # A 22vmin corner mark wants ~240px at 1080p; a 60vmin watermark ~650px.
    if entry["place"] == "watermark" and longest < 650:
        return (f"{filename} is {longest}px, good in a corner, soft as a "
                "watermark.")
    if entry["place"] != "cover" and ext in (".jpg", ".jpeg"):
        return (f"{filename} has no transparent background, so it will show as "
                "a rectangle. Save it as a PNG with transparency, or use it as "
                "a full background.")
    return None


def _process_art(source_path, entry, derived_colors) -> tuple[bytes, str, str]:
    """Process one art file, using the cache when the key matches.

    Returns (bytes, extension, diagnostic). The diagnostic is None when usable;
    otherwise it is a plain-sentence message with an obvious next step, and the
    caller still renders (degrading to the gradient ornament).
    """
    ext = os.path.splitext(source_path)[1].lower()
    try:
        stat = os.stat(source_path)
        mtime, size = stat.st_mtime, stat.st_size
    except OSError:
        return b"", ext, f"Could not read {os.path.basename(source_path)}."
    key = _art_cache_key(source_path, mtime, size, entry)
    cache_path = _art_cache_path(key, ext)
    if os.path.isfile(cache_path):
        try:
            with open(cache_path, "rb") as handle:
                return handle.read(), ext, _art_diagnostic(source_path, entry)
        except OSError as exc:
            operational_log.emit("panels.art_cache_read", "failed", error_class=type(exc))
    if ext == ".svg":
        data, out_ext, diagnostic = _process_svg(source_path, entry, derived_colors)
    else:
        data, out_ext, diagnostic = _process_raster(source_path, entry)
    # A processing failure (unreadable, no viewBox) is the primary diagnostic;
    # otherwise report the "will not look good" diagnostic for this placement.
    if not diagnostic:
        diagnostic = _art_diagnostic(source_path, entry)
    if data:
        try:
            os.makedirs(art_cache_dir(), exist_ok=True)
            with open(_art_cache_path(key, out_ext), "wb") as handle:
                handle.write(data)
        except OSError as exc:
            operational_log.emit("panels.art_cache_write", "failed", error_class=type(exc))
    return data, out_ext, diagnostic


def load_custom_themes(*, root=None, builtin_keys=BUILTIN_KEYS) -> dict:
    """Every usable custom theme, plus why any file was skipped.

    Never raises. A half-written or hand-mangled file must not take a saved
    board down, so it is skipped and reported while the rest still render.
    """
    directory = workspace.panel_themes_dir(root)
    themes, problems = [], []
    if not directory or not os.path.isdir(workspace.extended_path(directory)):
        return {"themes": [], "problems": problems}
    try:
        names = sorted(name for name in os.listdir(workspace.extended_path(directory))
                       if name.lower().endswith(".json"))
    except OSError as error:
        return {"themes": [], "problems": [{"file": directory, "error": str(error)}]}

    seen = set()
    for name in names:
        path = os.path.join(directory, name)
        try:
            with open(workspace.extended_path(path), encoding="utf-8") as handle:
                theme = normalize_theme(json.load(handle), builtin_keys=builtin_keys)
            # Zero-config attach: a file named after the theme attaches by
            # itself. Synthesized art is not written back to the theme file.
            synthesized = _synthesize_zero_config_art(theme, root=root)
            if synthesized:
                theme = dict(theme, art=synthesized)
            derive(theme)          # a theme that cannot derive cannot be offered
        except (OSError, TypeError, ValueError) as error:
            problems.append({"file": name, "error": str(error)})
            continue
        if theme["key"] in seen:
            problems.append({"file": name, "error":
                             f"skipped: {theme['key']!r} is already defined by another file"})
            continue
        seen.add(theme["key"])
        themes.append(theme)
    themes.sort(key=lambda entry: entry["label"].casefold())
    return {"themes": themes, "problems": problems}


def _atomic_write(theme: dict, *, root=None) -> dict:
    path = theme_path(theme["key"], root)
    if not path:
        raise ThemeError("workspace_not_configured")
    directory = workspace.extended_path(os.path.dirname(path))
    os.makedirs(directory, exist_ok=True)
    payload = json.dumps(theme, indent=2, ensure_ascii=False,
                         sort_keys=True).encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{theme['key']}-",
                                             suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, workspace.extended_path(path))
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return copy.deepcopy(theme)


# ── preview and apply ─────────────────────────────────────────────────────

def preview_digest(preview: dict) -> str:
    return hashlib.sha256(_canonical(preview.get("theme"))).hexdigest()


def build_preview(*, key, label, font=DEFAULT_FONT, ornament=DEFAULT_ORNAMENT,
                  colors=None, art=None, authored_by="assistant", root=None,
                  builtin_keys=BUILTIN_KEYS) -> dict:
    """The exact theme that apply would write, with its measured palette.

    Never writes. The digest covers the stored theme only, so a preview stays
    valid as long as the thing being written has not changed.
    """
    theme = normalize_theme({
        "version": VERSION, "key": key, "label": label, "font": font,
        "ornament": ornament, "colors": colors or {}, "art": art,
        "authored_by": authored_by,
    }, builtin_keys=builtin_keys)
    existing = load_custom_themes(root=root, builtin_keys=builtin_keys)
    replaces = next((entry for entry in existing["themes"]
                     if entry["key"] == theme["key"]), None)
    preview = {
        "theme": theme,
        "replaces": {"key": replaces["key"], "label": replaces["label"]} if replaces else None,
        **derive(theme),
    }
    preview["css"] = theme_css(theme)
    preview["digest"] = preview_digest(preview)
    return preview


def apply_preview(*, preview: dict, preview_digest_value: str, root=None,
                  builtin_keys=BUILTIN_KEYS) -> dict:
    """Write exactly the previewed theme, or refuse."""
    if not isinstance(preview, dict):
        raise ThemeError("preview must be the object returned by preview_panel_theme")
    if not HEX_DIGEST.match(str(preview_digest_value or "")):
        raise ThemeError("preview_digest must be the digest from the preview")
    if preview_digest(preview) != preview_digest_value:
        raise ThemeError("preview_digest does not match this preview. Build a "
                         "fresh preview and apply that.")
    theme = normalize_theme(preview.get("theme"), builtin_keys=builtin_keys)
    derive(theme)
    with _STORE_LOCK:
        current = load_custom_themes(root=root, builtin_keys=builtin_keys)
        replacing = any(entry["key"] == theme["key"] for entry in current["themes"])
        written = _atomic_write(theme, root=root)
    return {"theme": written, "replaced": replacing,
            "path": theme_path(theme["key"], root)}


def delete_theme(key: str, *, root=None) -> dict:
    """Remove one custom theme file. Built-ins are not reachable from here."""
    normalized = normalize_key(key)
    path = theme_path(normalized, root)
    if not path:
        raise ThemeError("workspace_not_configured")
    with _STORE_LOCK:
        if not os.path.isfile(workspace.extended_path(path)):
            raise ThemeError(f"no custom theme named {normalized!r}")
        os.unlink(workspace.extended_path(path))
    return {"key": normalized, "deleted": True}
