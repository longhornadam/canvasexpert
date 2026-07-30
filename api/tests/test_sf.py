"""Tests for SlideForge parsing and validation (sf.py)."""
import pytest
from api.webui import sf


class TestSFParsing:
    """Test envelope parsing."""

    def test_parse_file_missing(self):
        data, problems = sf.parse_file("/nonexistent/path.txt")
        assert data is None
        assert len(problems) > 0
        assert "cannot read file" in problems[0]

    def test_parse_no_envelope(self):
        data, problems = sf.parse("""
Some text without the envelope.
{"version": "1.0-json"}
""")
        assert data is None
        assert "no <SLIDEFORGE_JSON>" in problems[0]

    def test_parse_invalid_json(self):
        data, problems = sf.parse("""
<SLIDEFORGE_JSON>
{"version": "1.0-json", "type": "DECK", invalid json}
</SLIDEFORGE_JSON>
""")
        assert data is None
        assert "invalid JSON" in problems[0]

    def test_parse_valid_minimal(self):
        text = """
<SLIDEFORGE_JSON>
{"version": "1.0-json", "type": "DECK", "date": "2026-08-14", "title": "Test"}
</SLIDEFORGE_JSON>
"""
        data, problems = sf.parse(text)
        assert data is not None
        assert data["version"] == "1.0-json"


class TestSFValidation:
    """Test validation rules."""

    def test_version_required(self):
        data = {"type": "DECK", "date": "2026-08-14", "title": "Test", "slides": []}
        problems = sf.validate(data)
        assert any("version" in p for p in problems)

    def test_version_must_match(self):
        data = {"version": "2.0", "type": "DECK", "date": "2026-08-14",
                "title": "Test", "slides": []}
        problems = sf.validate(data)
        assert any("version" in p and "1.0-json" in p for p in problems)

    def test_type_required(self):
        data = {"version": "1.0-json", "date": "2026-08-14", "title": "Test", "slides": []}
        problems = sf.validate(data)
        assert any("type" in p for p in problems)

    def test_type_must_be_deck(self):
        data = {"version": "1.0-json", "type": "PAGE", "date": "2026-08-14",
                "title": "Test", "slides": []}
        problems = sf.validate(data)
        assert any("DECK" in p for p in problems)

    def test_date_required(self):
        data = {"version": "1.0-json", "type": "DECK", "title": "Test", "slides": []}
        problems = sf.validate(data)
        assert any("date" in p for p in problems)

    def test_date_format_yyyy_mm_dd(self):
        # Invalid formats
        for bad_date in ["2026-8-14", "14-08-2026", "2026/08/14", ""]:
            data = {"version": "1.0-json", "type": "DECK", "date": bad_date,
                    "title": "Test", "slides": []}
            problems = sf.validate(data)
            assert any("date" in p for p in problems)

        # Valid format
        data = {"version": "1.0-json", "type": "DECK", "date": "2026-08-14",
                "title": "Test", "slides": []}
        problems = sf.validate(data)
        assert not any("date" in p for p in problems)

    def test_title_required(self):
        data = {"version": "1.0-json", "type": "DECK", "date": "2026-08-14", "slides": []}
        problems = sf.validate(data)
        assert any("title" in p for p in problems)

    def test_title_cannot_be_empty_string(self):
        data = {"version": "1.0-json", "type": "DECK", "date": "2026-08-14",
                "title": "", "slides": []}
        problems = sf.validate(data)
        assert any("title" in p for p in problems)

    def test_slides_required_and_nonempty(self):
        # Missing
        data = {"version": "1.0-json", "type": "DECK", "date": "2026-08-14", "title": "Test"}
        problems = sf.validate(data)
        assert any("slides" in p for p in problems)

        # Empty array
        data = {"version": "1.0-json", "type": "DECK", "date": "2026-08-14",
                "title": "Test", "slides": []}
        problems = sf.validate(data)
        assert any("slides" in p for p in problems)

    def test_slide_id_unique(self):
        data = {
            "version": "1.0-json", "type": "DECK", "date": "2026-08-14", "title": "Test",
            "slides": [
                {"id": "s1", "block": "1st", "layout": "title_body", "title": "A"},
                {"id": "s1", "block": "1st", "layout": "title_body", "title": "B"},
            ]
        }
        problems = sf.validate(data)
        assert any("duplicate" in p for p in problems)

    def test_slide_block_required(self):
        data = {
            "version": "1.0-json", "type": "DECK", "date": "2026-08-14", "title": "Test",
            "slides": [
                {"id": "s1", "layout": "title_body", "title": "A"},
            ]
        }
        problems = sf.validate(data)
        assert any("block" in p for p in problems)

    def test_slide_block_nonempty(self):
        data = {
            "version": "1.0-json", "type": "DECK", "date": "2026-08-14", "title": "Test",
            "slides": [
                {"id": "s1", "block": "", "layout": "title_body", "title": "A"},
            ]
        }
        problems = sf.validate(data)
        assert any("block" in p for p in problems)

    def test_slide_layout_valid_values(self):
        valid_layouts = ["title_body", "title_only", "bulleted"]
        for layout in valid_layouts:
            data = {
                "version": "1.0-json", "type": "DECK", "date": "2026-08-14", "title": "Test",
                "slides": [
                    {"id": "s1", "block": "1st", "layout": layout, "title": "A"},
                ]
            }
            problems = sf.validate(data)
            assert not any("layout" in p for p in problems)

        # Invalid layout
        data = {
            "version": "1.0-json", "type": "DECK", "date": "2026-08-14", "title": "Test",
            "slides": [
                {"id": "s1", "block": "1st", "layout": "invalid", "title": "A"},
            ]
        }
        problems = sf.validate(data)
        assert any("layout" in p for p in problems)

    def test_feed_key_rejected(self):
        # Top-level feed
        data = {
            "version": "1.0-json", "type": "DECK", "date": "2026-08-14", "title": "Test",
            "slides": [{"id": "s1", "block": "1st", "layout": "title_body", "title": "A"}],
            "feed": []
        }
        problems = sf.validate(data)
        assert any("feed" in p for p in problems)

        # Slide-level feed
        data = {
            "version": "1.0-json", "type": "DECK", "date": "2026-08-14", "title": "Test",
            "slides": [
                {"id": "s1", "block": "1st", "layout": "title_body", "title": "A", "feed": []}
            ]
        }
        problems = sf.validate(data)
        assert any("feed" in p for p in problems)

    def test_unknown_toplevel_keys_rejected(self):
        data = {
            "version": "1.0-json", "type": "DECK", "date": "2026-08-14", "title": "Test",
            "slides": [{"id": "s1", "block": "1st", "layout": "title_body", "title": "A"}],
            "extra_field": "should cause error"
        }
        problems = sf.validate(data)
        assert any("unknown" in p and "extra_field" in p for p in problems)

    def test_widget_id_unique(self):
        data = {
            "version": "1.0-json", "type": "DECK", "date": "2026-08-14", "title": "Test",
            "widgets": [
                {"id": "w1", "scope": "deck", "kind": "timer", "params": {"duration_seconds": 60}},
                {"id": "w1", "scope": "deck", "kind": "timer", "params": {"duration_seconds": 60}},
            ],
            "slides": [
                {"id": "s1", "block": "1st", "layout": "title_body", "title": "A"},
            ]
        }
        problems = sf.validate(data)
        assert any("duplicate" in p for p in problems)

    def test_widget_scope_valid(self):
        for scope in ["deck", "slide"]:
            data = {
                "version": "1.0-json", "type": "DECK", "date": "2026-08-14", "title": "Test",
                "widgets": [
                    {"id": "w1", "scope": scope, "kind": "timer", "params": {"duration_seconds": 60}},
                ],
                "slides": [
                    {"id": "s1", "block": "1st", "layout": "title_body", "title": "A"},
                ]
            }
            problems = sf.validate(data)
            assert not any("scope" in p for p in problems)

        # Invalid scope
        data = {
            "version": "1.0-json", "type": "DECK", "date": "2026-08-14", "title": "Test",
            "widgets": [
                {"id": "w1", "scope": "invalid", "kind": "timer", "params": {"duration_seconds": 60}},
            ],
            "slides": [
                {"id": "s1", "block": "1st", "layout": "title_body", "title": "A"},
            ]
        }
        problems = sf.validate(data)
        assert any("scope" in p for p in problems)

    def test_widget_kind_must_be_timer(self):
        data = {
            "version": "1.0-json", "type": "DECK", "date": "2026-08-14", "title": "Test",
            "widgets": [
                {"id": "w1", "scope": "deck", "kind": "invalid", "params": {}},
            ],
            "slides": [
                {"id": "s1", "block": "1st", "layout": "title_body", "title": "A"},
            ]
        }
        problems = sf.validate(data)
        assert any("kind" in p for p in problems)

    def test_timer_duration_seconds_valid_range(self):
        # Valid durations
        for duration in [1, 300, 3600, 86400]:
            data = {
                "version": "1.0-json", "type": "DECK", "date": "2026-08-14", "title": "Test",
                "widgets": [
                    {"id": "w1", "scope": "deck", "kind": "timer", "params": {"duration_seconds": duration}},
                ],
                "slides": [
                    {"id": "s1", "block": "1st", "layout": "title_body", "title": "A"},
                ]
            }
            problems = sf.validate(data)
            assert not any("duration" in p for p in problems)

        # Invalid durations
        for duration in [0, -1, 86401, "300", 3.5]:
            data = {
                "version": "1.0-json", "type": "DECK", "date": "2026-08-14", "title": "Test",
                "widgets": [
                    {"id": "w1", "scope": "deck", "kind": "timer", "params": {"duration_seconds": duration}},
                ],
                "slides": [
                    {"id": "s1", "block": "1st", "layout": "title_body", "title": "A"},
                ]
            }
            problems = sf.validate(data)
            assert any("duration" in p for p in problems)

    def test_slide_widgets_must_exist(self):
        data = {
            "version": "1.0-json", "type": "DECK", "date": "2026-08-14", "title": "Test",
            "widgets": [
                {"id": "w1", "scope": "deck", "kind": "timer", "params": {"duration_seconds": 60}},
            ],
            "slides": [
                {"id": "s1", "block": "1st", "layout": "title_body", "title": "A",
                 "widgets": ["w1", "w2"]},
            ]
        }
        problems = sf.validate(data)
        assert any("unknown widget" in p for p in problems)

    def test_valid_minimal_deck(self):
        data = {
            "version": "1.0-json",
            "type": "DECK",
            "date": "2026-08-14",
            "title": "Test Deck",
            "slides": [
                {"id": "s1", "block": "1st Period", "layout": "title_body", "title": "Welcome"},
            ]
        }
        problems = sf.validate(data)
        assert len(problems) == 0

    def test_valid_complex_deck(self):
        data = {
            "version": "1.0-json",
            "type": "DECK",
            "date": "2026-08-14",
            "title": "Thursday Lesson",
            "widgets": [
                {"id": "timer1", "scope": "deck", "kind": "timer",
                 "params": {"duration_seconds": 300, "label": "Bell work", "autostart": True}},
                {"id": "timer2", "scope": "slide", "kind": "timer",
                 "params": {"duration_seconds": 600}},
            ],
            "slides": [
                {"id": "welcome", "block": "1st Period", "layout": "title_body",
                 "title": "Welcome!", "body": "Start bell work",
                 "widgets": ["timer1"]},
                {"id": "quiz-info", "block": "1st Period", "layout": "bulleted",
                 "title": "Quiz Rules",
                 "body": "Pencils only\nNo phones\nRaise hand",
                 "widgets": ["timer2"]},
                {"id": "closing", "block": "1st Period", "layout": "title_only",
                 "title": "Good luck!", "body": "", "widgets": []},
            ]
        }
        problems = sf.validate(data)
        assert len(problems) == 0
