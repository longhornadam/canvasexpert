"""Publishing the pseudonym-only profile into CanvasExpert's AI zone."""

import json

import pytest

from api.dataforge import profile_export


class _Paths:
    def __init__(self, tmp_path):
        self.data_dir = tmp_path
        self.output_dir = tmp_path / "output"
        self.history_dir = tmp_path / "history"


def _snapshot(paths, snap_id="s1"):
    paths.history_dir.mkdir(parents=True, exist_ok=True)
    (paths.history_dir / f"{snap_id}.json").write_text(json.dumps({
        "id": snap_id, "label": snap_id, "grade": "7", "type": "STAAR",
        "breakdown_type": "learning_standard", "standards": ["7.9(D)"],
        "date": "2026-09-01", "saved_at": "2026-09-01T00:00:00",
        "students": [{"n": "Student_420", "pct": 50.0, "missed": {"7.9(D)": 20.0}}],
    }), encoding="utf-8")


def test_publish_refuses_when_the_payload_would_leak(tmp_path, vault_identity):
    paths = _Paths(tmp_path)
    paths.history_dir.mkdir(parents=True, exist_ok=True)
    (paths.history_dir / "leaky.json").write_text(json.dumps({
        "id": "leaky", "label": "Retest for Claude Clauderino", "grade": "7",
        "type": "STAAR", "breakdown_type": "learning_standard",
        "standards": ["7.9(D)"], "date": "2026-09-01",
        "saved_at": "2026-09-01T00:00:00",
        "students": [{"n": "Student_420", "pct": 50.0, "missed": {"7.9(D)": 20.0}}],
    }), encoding="utf-8")

    provider = vault_identity(("Clauderino, Claude", "696969", "Sparky McGee"))

    with pytest.raises(profile_export.SharedPublishError, match="real identity"):
        profile_export.publish_profile(paths, anonymizer=provider)

    target = tmp_path / "CanvasExpert" / "For AI" / "DataForge"
    assert not target.exists()


def test_publish_writes_under_the_canvasexpert_ai_zone(tmp_path, vault_identity):
    paths = _Paths(tmp_path)
    _snapshot(paths)
    provider = vault_identity(("Clauderino, Claude", "696969", "Sparky McGee"))

    written = profile_export.publish_profile(paths, anonymizer=provider)
    expected = tmp_path / "CanvasExpert" / "For AI" / "DataForge" / profile_export.PROFILE_FILENAME
    assert written == expected

    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["format"] == profile_export.FORMAT
    assert payload["grouping"]["7.9(D)"] == ["Student_420"]
    assert "Clauderino" not in written.read_text(encoding="utf-8")
    assert "696969" not in written.read_text(encoding="utf-8")


def test_publish_never_includes_a_canvas_id_even_when_snapshots_carry_one(tmp_path, vault_identity):
    """A snapshot row carries a canvas_id for internal joining across a
    rename. This proves it never reaches the published (SAFE) profile,
    alongside the existing real-name/sis-id checks -- the invariant is no
    canvas_id, no sis_id, no real name, not just "no real name"."""
    paths = _Paths(tmp_path)
    paths.history_dir.mkdir(parents=True, exist_ok=True)
    (paths.history_dir / "s1.json").write_text(json.dumps({
        "id": "s1", "label": "s1", "grade": "7", "type": "STAAR",
        "breakdown_type": "learning_standard", "standards": ["7.9(D)"],
        "date": "2026-09-01", "saved_at": "2026-09-01T00:00:00",
        "students": [{"n": "Sparky McGee", "canvas_id": "canvas-1", "pct": 50.0, "missed": {"7.9(D)": 20.0}}],
    }), encoding="utf-8")
    provider = vault_identity(("Clauderino, Claude", "696969", "Sparky McGee"))

    written = profile_export.publish_profile(paths, anonymizer=provider)
    blob = written.read_text(encoding="utf-8")

    assert "canvas-1" not in blob
    assert "canvas_id" not in blob
    assert "sis_id" not in blob
    assert "696969" not in blob
    assert "Clauderino" not in blob
    payload = json.loads(blob)
    assert payload["students"]["Sparky McGee"]["assessments"] == 1


def test_publish_is_idempotent_and_leaves_no_temp_file(tmp_path):
    paths = _Paths(tmp_path)
    _snapshot(paths)

    first = profile_export.publish_profile(paths)
    second = profile_export.publish_profile(paths)
    assert first == second
    assert [p.name for p in first.parent.iterdir()] == [profile_export.PROFILE_FILENAME]
