"""Teacher-owned Panel themes: what the format refuses, and what it corrects.

The interesting cases here are not "does a valid theme work". They are the ones
where a theme file is authored by an LLM or hand-edited at 7am: a colour that
is really a CSS fragment, a palette nobody could read from the back of a room,
a file that is half-written, a key that would quietly replace a built-in.
"""
import json
import re
from pathlib import Path

import pytest

from api import panel_themes
from api.mcp_server import tools
from api.platform_services import workspace

GOOD = {"bg": "#f8fafc", "ink": "#101c30", "accent": "#123a70",
        "highlight": "#c8102e"}


@pytest.fixture
def themed_workspace(tmp_path, monkeypatch):
    """A workspace root with an empty Panel themes folder."""
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    directory = Path(workspace.panel_themes_dir())
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write(directory, name, payload):
    path = Path(directory) / name
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _authored(key="mine", label="Mine", **overrides):
    theme = {"version": 1, "key": key, "label": label, "font": "sans",
             "ornament": "grid", "colors": dict(GOOD)}
    theme.update(overrides)
    return theme


# ── what the format refuses ───────────────────────────────────────────────

def test_a_colour_that_is_really_a_css_fragment_is_refused():
    """The whole reason colours are parsed rather than passed through."""
    attack = '#fff; } html[data-panel-theme="ce"] { --bg: #000'
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.normalize_theme(_authored(colors=dict(GOOD, bg=attack)))


@pytest.mark.parametrize("value", [
    "red", "rgb(1,2,3)", "#ffff", "", "#12345g", None,
    "var(--ce-accent)", "url(http://example.invalid/x.png)",
    "#fff !important",
])
def test_only_plain_hex_is_a_colour(value):
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.normalize_theme(_authored(colors=dict(GOOD, accent=value)))


@pytest.mark.parametrize("key", [
    "my theme", "my/theme", 'a"b', "a{b", "-lead", "trail-",
    "", "x" * 33, "../escape", "mi\tne", "mi\nne",
])
def test_a_key_that_could_leave_the_selector_is_refused(key):
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.normalize_theme(_authored(key=key))


@pytest.mark.parametrize("key", ["Mine", "  MINE  ", "Test-Navy"])
def test_a_key_is_normalized_the_same_way_the_url_is(key):
    """``?theme=`` lowercases and trims, so authoring has to agree."""
    assert panel_themes.normalize_theme(_authored(key=key))["key"] == key.strip().lower()


def test_a_custom_theme_may_not_take_a_built_in_key():
    """Shadowing 'ce' would remove the default from a teacher's machine."""
    for key in sorted(panel_themes.BUILTIN_KEYS):
        with pytest.raises(panel_themes.ThemeError):
            panel_themes.normalize_theme(_authored(key=key))


def test_unknown_fields_and_colours_are_refused_rather_than_ignored():
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.normalize_theme(_authored(ornamment="grid"))
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.normalize_theme(_authored(colors=dict(GOOD, backgruond="#fff")))


def test_font_and_ornament_come_from_closed_sets():
    """A free-text font is how a webfont fetch would get onto a wall."""
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.normalize_theme(_authored(font="'Comic Sans MS', cursive"))
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.normalize_theme(_authored(ornament="url(http://x.invalid/a.svg)"))
    for font in panel_themes.FONTS:
        assert panel_themes.normalize_theme(_authored(font=font))["font"] == font
    for ornament in panel_themes.ORNAMENTS:
        theme = panel_themes.normalize_theme(_authored(ornament=ornament))
        assert theme["ornament"] == ornament


def test_a_missing_required_colour_is_named():
    with pytest.raises(panel_themes.ThemeError) as error:
        panel_themes.normalize_theme(_authored(colors={"bg": "#fff", "ink": "#000"}))
    assert "accent" in str(error.value)


@pytest.mark.parametrize("label", ["", "   ", "a" * 41, "<b>bold</b>", "line\nbreak"])
def test_labels_stay_plain_and_bounded(label):
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.normalize_theme(_authored(label=label))


def test_highlight_is_optional_and_defaults_to_accent():
    colors = {key: GOOD[key] for key in ("bg", "ink", "accent")}
    theme = panel_themes.normalize_theme(_authored(colors=colors))
    assert "highlight" not in theme["colors"]
    derived = panel_themes.derive(theme)
    assert derived["variables"]["--today-accent"]


# ── contrast is corrected, not trusted ────────────────────────────────────

def test_an_unreadable_palette_is_corrected_to_the_floor():
    """Pale grey on white is exactly what an LLM picks when asked for 'subtle'."""
    theme = panel_themes.normalize_theme(_authored(
        colors={"bg": "#ffffff", "ink": "#eeeeee", "accent": "#f4f4f4",
                "highlight": "#fbfbfb"}))
    derived = panel_themes.derive(theme)
    assert derived["adjustments"], "a pale palette must report corrections"
    assert derived["worst_ratio"] >= panel_themes.CONTRAST_FLOOR
    for name, ratio in derived["contrast"].items():
        assert ratio >= panel_themes.CONTRAST_FLOOR, name


def test_a_palette_that_already_reads_is_left_alone():
    derived = panel_themes.derive(panel_themes.normalize_theme(_authored()))
    moved = {entry["variable"] for entry in derived["adjustments"]}
    assert "--ink" not in moved
    assert derived["worst_ratio"] >= panel_themes.CONTRAST_FLOOR


def test_a_dark_theme_lifts_its_rows_and_still_reads():
    theme = panel_themes.normalize_theme(_authored(
        colors={"bg": "#10171b", "ink": "#cfe0e4", "accent": "#35d39a",
                "highlight": "#ffb648"}))
    derived = panel_themes.derive(theme)
    variables = derived["variables"]
    bg = panel_themes.parse_hex(variables["--bg"], "bg")
    row = panel_themes.parse_hex(variables["--row"], "row")
    assert panel_themes.luminance(row) > panel_themes.luminance(bg)
    assert derived["worst_ratio"] >= panel_themes.CONTRAST_FLOOR


def test_every_built_in_palette_would_also_pass_the_floor():
    """The floor is not stricter than the themes that already ship."""
    ce = panel_themes.normalize_theme(_authored(
        key="ce-like", label="CE like",
        colors={"bg": "#f4efe6", "ink": "#29251f", "accent": "#2f7d77",
                "highlight": "#d9893f"}))
    assert panel_themes.derive(ce)["worst_ratio"] >= panel_themes.CONTRAST_FLOOR


def test_contrast_maths_matches_the_wcag_reference_points():
    black, white = (0, 0, 0), (255, 255, 255)
    assert round(panel_themes.contrast(black, white), 1) == 21.0
    assert round(panel_themes.contrast(white, white), 1) == 1.0
    # #767676 on white is the canonical "just passes 4.5:1" pairing.
    assert 4.5 <= panel_themes.contrast((0x76, 0x76, 0x76), white) < 4.6


@pytest.mark.parametrize("bg", ["#ffffff", "#fffefd", "#f8fafc", "#f4efe6",
                                "#808080", "#0d1b33", "#000000"])
def test_rows_stay_distinguishable_from_the_page_at_any_lightness(bg):
    """Rows are the opaque bed row text sits on. If they collapse into --bg the
    banding that separates one row from the next is gone, and a projector shows
    one undifferentiated block. Near-white pages used to do exactly that."""
    ink = "#101c30" if panel_themes.luminance(
        panel_themes.parse_hex(bg, "bg")) > 0.4 else "#eef2f8"
    theme = panel_themes.normalize_theme(_authored(
        colors={"bg": bg, "ink": ink, "accent": "#123a70",
                "highlight": "#c8102e"}))
    derived = panel_themes.derive(theme)
    variables = derived["variables"]
    page = panel_themes.parse_hex(variables["--bg"], "bg")
    row = panel_themes.parse_hex(variables["--row"], "row")
    row_alt = panel_themes.parse_hex(variables["--row-alt"], "row-alt")
    for name, first, second in (("bg/row", page, row),
                                ("row/row-alt", row, row_alt)):
        separation = tuple(abs(a - b) for a, b in zip(first, second))
        assert min(separation) >= 3, (bg, name, separation)
    ink_rgb = panel_themes.parse_hex(variables["--ink"], "ink")
    for name, bed in (("bg", page), ("row", row), ("row-alt", row_alt)):
        assert panel_themes.contrast(ink_rgb, bed) >= panel_themes.CONTRAST_FLOOR, (
            bg, name)


def _text_bed_ceiling(variables: dict) -> float:
    """The best any single ink could do against --bg, --row, and --row-alt at
    once.

    For each of pure black and pure white, take the worst (minimum) contrast
    against the three beds; the higher of those two numbers is the ceiling
    no ink can beat, because moving a colour toward one extreme only ever
    trades contrast on one bed for contrast on another. This mirrors the
    ceiling ``derive()`` itself reports as ``floor_ceiling``.
    """
    beds = [panel_themes.parse_hex(variables[name], name)
            for name in ("--bg", "--row", "--row-alt")]
    black, white = (0, 0, 0), (255, 255, 255)
    best_black = min(panel_themes.contrast(black, bed) for bed in beds)
    best_white = min(panel_themes.contrast(white, bed) for bed in beds)
    return max(best_black, best_white)


@pytest.mark.parametrize("level", range(0, 256, 16))
def test_no_page_lightness_reports_below_the_floor(level):
    """derive() promises a 4.5:1 floor. Correcting against only the worst bed
    used to under-shoot on mid-tone pages, so the promise and the reported
    worst_ratio disagreed: on some mid-tone pages the three text beds spread
    far enough apart (the row lift) that no single ink clears 4.5 against all
    of them at once. Rather than hardcode which page levels that happens at,
    compute the ceiling each ink could actually reach against these beds and
    hold derive() to whichever is lower: the floor, or that ceiling.
    """
    bg = "#%02x%02x%02x" % (level, level, level)
    ink = "#101c30" if panel_themes.luminance(
        panel_themes.parse_hex(bg, "bg")) > 0.4 else "#eef2f8"
    theme = panel_themes.normalize_theme(_authored(
        colors={"bg": bg, "ink": ink, "accent": "#123a70",
                "highlight": "#c8102e"}))
    derived = panel_themes.derive(theme)
    ceiling = _text_bed_ceiling(derived["variables"])
    target = min(panel_themes.CONTRAST_FLOOR, ceiling)
    assert derived["worst_ratio"] >= target - 0.01, (
        bg, derived["worst_pair"], ceiling)


def test_an_unreachable_background_reports_its_ceiling_honestly():
    """bg #996633 is one of the palettes that cannot hold 4.5:1 against all
    three text beds no matter which ink is picked. derive() should say so
    rather than silently reporting a worst_ratio below the floor with no
    explanation."""
    theme = panel_themes.normalize_theme(_authored(
        colors={"bg": "#996633", "ink": "#101c30", "accent": "#123a70",
                "highlight": "#c8102e"}))
    derived = panel_themes.derive(theme)
    assert derived["floor_reachable"] is False
    assert 4.25 <= derived["floor_ceiling"] <= 4.35
    ceiling = _text_bed_ceiling(derived["variables"])
    assert derived["worst_ratio"] >= min(panel_themes.CONTRAST_FLOOR, ceiling) - 0.01


def test_a_normal_background_reports_the_floor_as_reachable():
    derived = panel_themes.derive(panel_themes.normalize_theme(_authored(colors=dict(GOOD))))
    assert derived["floor_reachable"] is True
    assert derived["floor_ceiling"] >= panel_themes.CONTRAST_FLOOR


# ── generated CSS cannot break the kit ────────────────────────────────────

KIT_CLASSES = (".p-row", ".p-body", ".p-head", ".p-foot", ".p-stack",
               ".p-title", ".panel", "body", "html {")


def test_generated_css_only_ever_targets_the_theme_attribute():
    css = panel_themes.theme_css(panel_themes.normalize_theme(_authored()))
    assert css.count("{") == 1 and css.count("}") == 1
    assert css.startswith('html[data-panel-theme="mine"] {')
    for selector in KIT_CLASSES:
        assert selector not in css, selector


def test_generated_css_declares_custom_properties_and_nothing_else():
    """The sizing model is measured from the body box. A generated theme that
    could emit padding or font-size would change what a Panel shows."""
    for ornament in panel_themes.ORNAMENTS:
        css = panel_themes.theme_css(
            panel_themes.normalize_theme(_authored(ornament=ornament)))
        body = css.split("{", 1)[1].rsplit("}", 1)[0]
        declarations = [line.strip() for line in body.splitlines() if line.strip()]
        assert declarations
        for declaration in declarations:
            assert declaration.startswith("--"), (ornament, declaration)


_ART_URL_RE = re.compile(
    r"^/panels/theme-art/[a-z0-9-]+/\d+\.(svg|png|jpe?g|webp)\?v=[0-9a-f]+$")


def test_nothing_in_a_theme_can_reach_the_internet():
    """A Panel on a wall never waits on the internet. The only url() a theme
    may emit is a same-origin, hashed, immutable reference to the local art
    route -- exactly like panel.css reading a file off disk."""
    for ornament in panel_themes.ORNAMENTS:
        css = panel_themes.theme_css(
            panel_themes.normalize_theme(_authored(ornament=ornament)))
        lowered = css.lower()
        for forbidden in ("http", "//", "@import", "image-set", "src:"):
            assert forbidden not in lowered, (ornament, forbidden)
        for url in re.findall(r"url\(\"([^\"]+)\"\)", css):
            assert _ART_URL_RE.match(url), (ornament, url)


def test_a_label_never_reaches_the_stylesheet():
    theme = panel_themes.normalize_theme(
        _authored(label="} .p-row { padding: 99px } x"))
    css = panel_themes.theme_css(theme)
    assert "padding" not in css
    assert ".p-row" not in css


def test_every_variable_the_kit_reads_is_emitted():
    """A half-set palette shows one built-in's colours through the gaps."""
    variables = panel_themes.derive(panel_themes.normalize_theme(_authored()))["variables"]
    for name in ("--panel-font", "--bg", "--ink", "--title", "--muted", "--rule",
                 "--accent", "--row", "--row-alt", "--pill-bg", "--pill-ink",
                 "--today-bg", "--today-accent", "--today-ink", "--when-ink",
                 "--warn-ink"):
        assert name in variables, name


# ── the loader is forgiving in the right direction ────────────────────────

def test_no_workspace_and_no_folder_are_both_quiet(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "workspace_root", lambda: None)
    assert panel_themes.load_custom_themes() == {"themes": [], "problems": []}
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    assert panel_themes.load_custom_themes()["themes"] == []


def test_one_bad_file_does_not_take_the_others_down(themed_workspace):
    _write(themed_workspace, "good.json", _authored(key="good", label="Good"))
    _write(themed_workspace, "truncated.json", '{"version": 1, "key": "trunc"')
    _write(themed_workspace, "ce.json", _authored(key="ce", label="Shadow"))
    _write(themed_workspace, "wrong.json", _authored(key="wrong", font="Papyrus"))
    _write(themed_workspace, "notes.txt", "not a theme at all")

    loaded = panel_themes.load_custom_themes()
    assert [theme["key"] for theme in loaded["themes"]] == ["good"]
    assert len(loaded["problems"]) == 3
    assert {problem["file"] for problem in loaded["problems"]} == {
        "truncated.json", "ce.json", "wrong.json"}


def test_two_files_claiming_one_key_keeps_the_first_and_says_so(themed_workspace):
    _write(themed_workspace, "a-first.json", _authored(key="dup", label="First"))
    _write(themed_workspace, "b-second.json", _authored(key="dup", label="Second"))
    loaded = panel_themes.load_custom_themes()
    assert [theme["label"] for theme in loaded["themes"]] == ["First"]
    assert "already defined" in loaded["problems"][0]["error"]


def test_the_list_is_ordered_by_label_for_the_dropdown(themed_workspace):
    for key, label in (("z", "Apple"), ("a", "zebra"), ("m", "Mango")):
        _write(themed_workspace, f"{key}.json", _authored(key=key, label=label))
    loaded = panel_themes.load_custom_themes()
    assert [theme["label"] for theme in loaded["themes"]] == ["Apple", "Mango", "zebra"]


# ── preview and apply ─────────────────────────────────────────────────────

def test_preview_writes_nothing(themed_workspace):
    panel_themes.build_preview(key="mine", label="Mine", colors=GOOD)
    assert list(Path(themed_workspace).iterdir()) == []


def test_apply_writes_the_previewed_theme_and_the_loader_sees_it(themed_workspace):
    preview = panel_themes.build_preview(key="mine", label="Mine", colors=GOOD)
    result = panel_themes.apply_preview(preview=preview,
                                       preview_digest_value=preview["digest"])
    assert result["replaced"] is False
    assert Path(result["path"]).name == "mine.json"
    loaded = panel_themes.load_custom_themes()
    assert [theme["key"] for theme in loaded["themes"]] == ["mine"]
    assert loaded["problems"] == []


def test_a_tampered_preview_is_refused(themed_workspace):
    preview = panel_themes.build_preview(key="mine", label="Mine", colors=GOOD)
    digest = preview["digest"]
    preview["theme"]["colors"]["bg"] = "#000000"
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.apply_preview(preview=preview, preview_digest_value=digest)
    assert list(Path(themed_workspace).iterdir()) == []


@pytest.mark.parametrize("digest", ["", None, "nope", "a" * 64])
def test_apply_needs_the_real_digest(themed_workspace, digest):
    preview = panel_themes.build_preview(key="mine", label="Mine", colors=GOOD)
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.apply_preview(preview=preview, preview_digest_value=digest)


def test_reapplying_the_same_key_replaces_and_reports_it(themed_workspace):
    first = panel_themes.build_preview(key="mine", label="Mine", colors=GOOD)
    panel_themes.apply_preview(preview=first, preview_digest_value=first["digest"])
    second = panel_themes.build_preview(key="mine", label="Mine v2", colors=GOOD)
    assert second["replaces"] == {"key": "mine", "label": "Mine"}
    result = panel_themes.apply_preview(preview=second,
                                        preview_digest_value=second["digest"])
    assert result["replaced"] is True
    loaded = panel_themes.load_custom_themes()
    assert [theme["label"] for theme in loaded["themes"]] == ["Mine v2"]


def test_delete_removes_one_theme_and_refuses_the_unknown(themed_workspace):
    preview = panel_themes.build_preview(key="mine", label="Mine", colors=GOOD)
    panel_themes.apply_preview(preview=preview,
                               preview_digest_value=preview["digest"])
    assert panel_themes.delete_theme("mine")["deleted"] is True
    assert panel_themes.load_custom_themes()["themes"] == []
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.delete_theme("mine")


def test_a_key_cannot_escape_the_themes_folder(themed_workspace):
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.theme_path("../../evil")
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.delete_theme("../Learning Objectives")


# ── the MCP surface ───────────────────────────────────────────────────────

def test_the_contract_describes_only_what_the_format_accepts():
    contract = tools.get_theme_contract()
    assert contract["ok"] is True
    assert sorted(contract["you_set"]["font"]) == sorted(panel_themes.FONTS)
    assert contract["you_set"]["ornament"] == list(panel_themes.ORNAMENTS)
    assert contract["builtin_keys"] == sorted(panel_themes.BUILTIN_KEYS)
    example = panel_themes.normalize_theme(dict(contract["example"], version=1,
                                                label="Example"))
    assert panel_themes.derive(example)["worst_ratio"] >= panel_themes.CONTRAST_FLOOR


def test_the_mcp_round_trip_lands_a_usable_theme(themed_workspace):
    preview = tools.preview_panel_theme("test-navy", "Test navy", GOOD)
    assert preview["ok"] is True
    applied = tools.apply_panel_theme(preview, preview["digest"])
    assert applied == {"ok": True, "key": "test-navy",
                       "label": "Test navy", "replaced": False,
                       "url_hint": "?theme=test-navy"}
    listed = tools.list_panel_themes()
    assert listed["custom_count"] == 1
    assert ["test-navy", "Test navy", "yours"] in [
        row[:3] for row in listed["themes"]["rows"]]


def test_mcp_tools_report_errors_rather_than_raising(themed_workspace):
    assert tools.preview_panel_theme("ce", "Shadow", GOOD)["ok"] is False
    assert tools.preview_panel_theme("ok-key", "Bad", {"bg": "red"})["ok"] is False
    assert tools.apply_panel_theme({"theme": {}}, "x")["ok"] is False
    assert tools.delete_panel_theme("never-existed")["ok"] is False


def test_mcp_cannot_delete_a_built_in():
    for key in sorted(panel_themes.BUILTIN_KEYS):
        result = tools.delete_panel_theme(key)
        assert result["ok"] is False
        assert "built-in" in result["error"]


def test_preview_notes_a_background_that_cannot_hold_the_floor(themed_workspace):
    """Diagnose, never refuse: the unreachable palette still previews cleanly,
    it just carries a plain sentence the assistant can pass on."""
    preview = tools.preview_panel_theme(
        "hardbg", "Hard bg",
        {"bg": "#996633", "ink": "#101c30", "accent": "#123a70",
         "highlight": "#c8102e"})
    assert preview["ok"] is True
    assert preview["floor_reachable"] is False
    assert preview["notes"], "an unreachable floor should be named in notes"
    note = preview["notes"][0]
    assert "4.5" in note
    assert str(preview["floor_ceiling"]) in note


def test_preview_carries_no_note_when_the_floor_is_reachable(themed_workspace):
    preview = tools.preview_panel_theme("softbg", "Soft bg", GOOD)
    assert preview["ok"] is True
    assert preview["floor_reachable"] is True
    assert "notes" not in preview


# ── the seeded Bobcats themes ─────────────────────────────────────────────

@pytest.mark.parametrize("name", ["bobcats.json", "bobcats-night.json"])
def test_each_seeded_bobcats_theme_parses_derives_and_reads(name):
    """A shipped theme must stay legible. If a future derivation change makes
    one of these illegible, that is a regression, not a new authoring choice."""
    path = Path("api/default_docs/Panels/Themes") / name
    assert path.exists(), f"seeded theme missing: {path}"
    theme = panel_themes.normalize_theme(json.loads(path.read_text(encoding="utf-8")))
    derived = panel_themes.derive(theme)
    assert derived["worst_ratio"] >= panel_themes.CONTRAST_FLOOR
    assert theme["key"] == name.removesuffix(".json")


# ── theme art ─────────────────────────────────────────────────────────────

def _art_theme(**overrides):
    theme = _authored(key="artful", label="Artful")
    theme["art"] = [{"file": "leaf.svg", "place": "corner-br", "size": 22,
                     "opacity": 0.5, "recolor": "accent"}]
    theme.update(overrides)
    return theme


def _write_art(themed_workspace, name, content):
    art = Path(themed_workspace) / "art"
    art.mkdir(parents=True, exist_ok=True)
    path = art / name
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)
    return path


def test_art_field_is_validated_and_normalized():
    theme = panel_themes.normalize_theme(_art_theme())
    assert theme["art"][0]["place"] == "corner-br"
    assert theme["art"][0]["size"] == 22
    assert theme["art"][0]["opacity"] == 0.5
    assert theme["art"][0]["recolor"] == "accent"


@pytest.mark.parametrize("filename", ["../escape.svg", "a/b.svg", "a\\b.svg",
                                      "..svg", "leaf.svg/.."])
def test_art_filename_with_separator_or_dotdot_is_refused(filename):
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.normalize_theme(_art_theme(art=[{"file": filename}]))


def test_art_unknown_field_is_refused():
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.normalize_theme(
            _art_theme(art=[{"file": "leaf.svg", "bogus": 1}]))


def test_art_size_and_opacity_are_clamped():
    theme = panel_themes.normalize_theme(_art_theme(art=[
        {"file": "leaf.svg", "place": "corner-br", "size": 999, "opacity": 5}]))
    assert theme["art"][0]["size"] == panel_themes.ART_MAX_SIZE
    assert theme["art"][0]["opacity"] == panel_themes.ART_MAX_OPACITY
    theme = panel_themes.normalize_theme(_art_theme(art=[
        {"file": "leaf.svg", "place": "corner-br", "size": 0, "opacity": 0}]))
    assert theme["art"][0]["size"] == panel_themes.ART_MIN_SIZE
    assert theme["art"][0]["opacity"] == panel_themes.ART_MIN_OPACITY


def test_art_place_must_come_from_the_closed_set():
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.normalize_theme(_art_theme(art=[
            {"file": "leaf.svg", "place": "everywhere"}]))


def test_art_recolor_must_come_from_the_closed_set():
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.normalize_theme(_art_theme(art=[
            {"file": "leaf.svg", "recolor": "rainbow"}]))


def test_art_extension_must_be_accepted():
    with pytest.raises(panel_themes.ThemeError):
        panel_themes.normalize_theme(_art_theme(art=[
            {"file": "leaf.gif"}]))


def test_placement_compiles_to_expected_background_shorthand():
    cases = {
        "corner-tl": "no-repeat left -2vmin top -3vmin / 22vmin",
        "corner-tr": "no-repeat right -2vmin top -3vmin / 22vmin",
        "corner-bl": "no-repeat left -2vmin bottom -3vmin / 22vmin",
        "corner-br": "no-repeat right -2vmin bottom -3vmin / 22vmin",
        "tile": "repeat 0 0 / 22vmin 22vmin",
        "band-bottom": "repeat-x left bottom / auto 22vmin",
        "watermark": "no-repeat center / 22vmin",
        "cover": "no-repeat center / cover",
    }
    for place, expected in cases.items():
        layers = panel_themes._placement_layers(
            {"place": place, "size": 22}, 22)
        assert expected in layers[0], (place, layers)


def test_scatter_compiles_to_three_layers():
    layers = panel_themes._placement_layers({"place": "scatter", "size": 22}, 22)
    assert len(layers) == 3


def test_art_layers_precede_gradient_layers(themed_workspace):
    _write_art(themed_workspace, "leaf.svg",
               '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
               '<path d="M0 0 L100 100" fill="#000"/></svg>')
    theme = panel_themes.normalize_theme(_art_theme())
    derived = panel_themes.derive(theme)
    ornament = derived["variables"]["--ornament"]
    assert "url(" in ornament
    assert ornament.index("url(") < ornament.index("repeating-linear-gradient")


def test_cover_emits_the_scrim(themed_workspace):
    _write_art(themed_workspace, "leaf.svg",
               '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
               '<rect width="100" height="100" fill="#000"/></svg>')
    theme = panel_themes.normalize_theme(_art_theme(art=[
        {"file": "leaf.svg", "place": "cover", "size": 22, "opacity": 0.5,
         "recolor": "accent"}]))
    derived = panel_themes.derive(theme)
    ornament = derived["variables"]["--ornament"]
    assert "linear-gradient" in ornament
    assert "cover" in ornament


def test_recolor_uses_the_derived_palette(themed_workspace):
    _write_art(themed_workspace, "leaf.svg",
               '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
               '<path d="M0 0 L100 100" fill="#000000"/></svg>')
    theme = panel_themes.normalize_theme(_art_theme(art=[
        {"file": "leaf.svg", "place": "corner-br", "size": 22, "opacity": 0.5,
         "recolor": "accent"}]))
    derived = panel_themes.derive(theme)
    accent = derived["variables"]["--accent"]
    data, _ext, _diag = panel_themes._process_art(
        _write_art(themed_workspace, "leaf.svg",
                   '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                   '<path d="M0 0 L100 100" fill="#000000"/></svg>'),
        theme["art"][0],
        {"bg": derived["variables"]["--bg"], "ink": derived["variables"]["--ink"],
         "accent": accent, "highlight": derived["variables"]["--today-accent"]})
    assert accent.lstrip("#").lower().encode() in data.lower()


def test_missing_art_file_degrades_with_a_named_problem(themed_workspace):
    theme = panel_themes.normalize_theme(_art_theme(art=[
        {"file": "missing.svg", "place": "corner-br", "size": 22,
         "opacity": 0.5, "recolor": "accent"}]))
    derived = panel_themes.derive(theme)
    assert derived.get("art_diagnostics")
    assert derived["art_diagnostics"][0]["file"] == "missing.svg"
    # The theme still renders with its gradient ornament.
    assert "--ornament" in derived["variables"]


def test_svg_cruft_and_coordinate_rounding_shrink_a_fixture(themed_workspace):
    bloated = ('<svg xmlns="http://www.w3.org/2000/svg" '
               'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd" '
               'viewBox="0 0 100 100"><metadata>editor cruft</metadata>'
               '<path sodipodi:type="arc" d="M0.123456789 0.987654321 '
               'L99.123456789 99.987654321" fill="#000"/></svg>')
    path = _write_art(themed_workspace, "leaf.svg", bloated)
    theme = panel_themes.normalize_theme(_art_theme())
    data, _ext, _diag = panel_themes._process_art(
        path, theme["art"][0],
        {"bg": "#fff", "ink": "#000", "accent": "#123a70", "highlight": "#c8102e"})
    text = data.decode("utf-8")
    assert "sodipodi" not in text
    assert "metadata" not in text
    assert "0.12" in text  # rounded
    assert "0.123456789" not in text


def test_raster_over_1600px_is_downscaled(themed_workspace):
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")
    import io
    image = Image.new("RGBA", (3200, 800), (10, 20, 30, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    path = _write_art(themed_workspace, "wide.png", buffer.getvalue())
    theme = panel_themes.normalize_theme(_art_theme(art=[
        {"file": "wide.png", "place": "corner-br", "size": 22, "opacity": 0.5,
         "recolor": "accent"}]))
    data, _ext, _diag = panel_themes._process_art(
        path, theme["art"][0],
        {"bg": "#fff", "ink": "#000", "accent": "#123a70", "highlight": "#c8102e"})
    with Image.open(io.BytesIO(data)) as out:
        assert max(out.size) <= panel_themes.ART_MAX_DIMENSION


def test_cache_is_keyed_so_changing_recolor_regenerates(themed_workspace):
    _write_art(themed_workspace, "leaf.svg",
               '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
               '<path d="M0 0 L100 100" fill="#000"/></svg>')
    path = Path(themed_workspace) / "art" / "leaf.svg"
    entry_a = {"file": "leaf.svg", "place": "corner-br", "size": 22,
               "opacity": 0.5, "recolor": "accent"}
    entry_b = {"file": "leaf.svg", "place": "corner-br", "size": 22,
               "opacity": 0.5, "recolor": "ink"}
    stat = path.stat()
    key_a = panel_themes._art_cache_key(str(path), stat.st_mtime, stat.st_size, entry_a)
    key_b = panel_themes._art_cache_key(str(path), stat.st_mtime, stat.st_size, entry_b)
    assert key_a != key_b


def test_generated_css_url_matches_the_art_pattern(themed_workspace):
    _write_art(themed_workspace, "leaf.svg",
               '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
               '<path d="M0 0 L100 100" fill="#000"/></svg>')
    theme = panel_themes.normalize_theme(_art_theme())
    css = panel_themes.theme_css(theme)
    for url in re.findall(r"url\(\"([^\"]+)\"\)", css):
        assert _ART_URL_RE.match(url), url


def test_theme_with_art_emits_only_custom_properties(themed_workspace):
    _write_art(themed_workspace, "leaf.svg",
               '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
               '<path d="M0 0 L100 100" fill="#000"/></svg>')
    theme = panel_themes.normalize_theme(_art_theme())
    css = panel_themes.theme_css(theme)
    body = css.split("{", 1)[1].rsplit("}", 1)[0]
    for declaration in body.splitlines():
        if declaration.strip():
            assert declaration.strip().startswith("--"), declaration


def test_zero_config_attach_synthesizes_an_entry(themed_workspace):
    _write_art(themed_workspace, "artful.svg",
               '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
               '<path d="M0 0 L100 100" fill="#000"/></svg>')
    _write(themed_workspace, "artful.json", _authored(key="artful", label="Artful"))
    loaded = panel_themes.load_custom_themes()
    assert loaded["themes"][0]["art"][0]["file"] == "artful.svg"
    assert loaded["themes"][0]["art"][0]["place"] == "corner-br"


def test_list_theme_art_reports_files_and_dimensions(themed_workspace):
    _write_art(themed_workspace, "leaf.svg",
               '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
               '<path d="M0 0 L100 100" fill="#000"/></svg>')
    result = panel_themes.list_theme_art()
    assert any(f["file"] == "leaf.svg" and f["viewBox"] == "0 0 100 100"
               for f in result["files"])
