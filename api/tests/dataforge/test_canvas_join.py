"""The pieces that let a DataForge pseudonym reach a Canvas student.

Two halves, deliberately separate:
  - the Identity Vault links a pseudonym to a local ID (PRIVATE, stays on the machine)
  - the standards profile is keyed by pseudonym only (SAFE, can travel)

Nothing here should ever put a real identity into the profile.
"""

import json

from api.dataforge import history_store, profile_export
from api.dataforge.eduphoria_parser import convert_to_json, pick_parser


class _Paths:
    """Minimal stand-in for paths.Paths."""

    def __init__(self, tmp_path):
        self.data_dir = tmp_path
        self.output_dir = tmp_path / "output"
        self.history_dir = tmp_path / "history"


# --- the safe half: the standards profile --------------------------------


def _snapshot(paths, snap_id, standards, students, when, breakdown="learning_standard"):
    d = paths.history_dir
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{snap_id}.json").write_text(json.dumps({
        "id": snap_id, "label": snap_id, "campus_code": "", "grade": "7",
        "type": "STAAR", "breakdown_type": breakdown, "standards": standards,
        "date": when, "saved_at": when + "T00:00:00", "students": students,
    }), encoding="utf-8")


def test_profile_marks_weak_standards(tmp_path):
    paths = _Paths(tmp_path)
    _snapshot(paths, "fall", ["7.2(B)", "7.9(D)"], [
        {"n": "Student_420", "pct": 80.0, "missed": {"7.9(D)": 40.0}},
    ], "2026-09-01")

    prof = profile_export.build_profile(paths)
    rec = prof["students"]["Student_420"]
    assert rec["standards"]["7.9(D)"]["weak"] is True
    assert rec["standards"]["7.2(B)"]["latest"] == 100.0, "covered but not missed = mastered"
    assert rec["standards"]["7.2(B)"]["weak"] is False
    assert rec["weak_standards"] == ["7.9(D)"]


def test_profile_tracks_a_standard_across_snapshots(tmp_path):
    paths = _Paths(tmp_path)
    _snapshot(paths, "fall", ["7.9(D)"], [
        {"n": "Student_420", "pct": 50.0, "missed": {"7.9(D)": 20.0}}], "2026-09-01")
    _snapshot(paths, "spring", ["7.9(D)"], [
        {"n": "Student_420", "pct": 90.0, "missed": {}}], "2027-03-01")

    entry = profile_export.build_profile(paths)["students"]["Student_420"]["standards"]["7.9(D)"]
    assert entry["attempts"] == 2
    assert entry["latest"] == 100.0, "the later snapshot wins"
    assert entry["weak"] is False
    assert entry["mean"] == 60.0


def test_profile_excludes_reporting_category_snapshots(tmp_path):
    """An RC average and a TEKS average are different measurements; tiering on
    a mix of them would be meaningless."""
    paths = _Paths(tmp_path)
    _snapshot(paths, "std", ["7.9(D)"], [
        {"n": "Student_420", "pct": 90.0, "missed": {}}], "2026-09-01")
    _snapshot(paths, "rc", ["R1", "R2"], [
        {"n": "Student_420", "pct": 90.0, "missed": {"R2": 50.0}}],
        "2026-09-02", breakdown="reporting_category")

    prof = profile_export.build_profile(paths)
    assert prof["snapshots_used"] == 1
    assert "R2" not in prof["students"]["Student_420"]["standards"]


def test_profile_pools_item_responses_with_standard_breakdowns(tmp_path):
    """Both report against TEKS codes, so they are the same grain and a
    student's history across the two must accumulate rather than split."""
    paths = _Paths(tmp_path)
    _snapshot(paths, "breakdown", ["7.9(D)"], [
        {"n": "Student_420", "pct": 50.0, "missed": {"7.9(D)": 20.0}}], "2026-09-01")
    _snapshot(paths, "responses", ["7.9(D)"], [
        {"n": "Student_420", "pct": 90.0, "missed": {}}],
        "2027-03-01", breakdown="item_response")

    prof = profile_export.build_profile(paths)
    assert prof["snapshots_used"] == 2
    assert prof["students"]["Student_420"]["standards"]["7.9(D)"]["attempts"] == 2


def test_reporting_category_grain_is_available_on_request(tmp_path):
    paths = _Paths(tmp_path)
    _snapshot(paths, "rc", ["R1", "R2"], [
        {"n": "Student_420", "pct": 90.0, "missed": {"R2": 50.0}}],
        "2026-09-02", breakdown="reporting_category")

    prof = profile_export.build_profile(paths, reporting_categories=True)
    assert prof["grain"] == "reporting_category"
    assert prof["students"]["Student_420"]["weak_standards"] == ["R2"]


def test_profile_reports_snapshots_missing_a_standard_list(tmp_path):
    """Snapshots written before the standard list was recorded can still show
    misses, but not mastery. Say so rather than implying full coverage."""
    paths = _Paths(tmp_path)
    _snapshot(paths, "legacy", [], [
        {"n": "Student_420", "pct": 50.0, "missed": {"7.9(D)": 20.0}}], "2026-09-01")
    prof = profile_export.build_profile(paths)
    assert prof["snapshots_without_standard_list"] == 1
    assert prof["students"]["Student_420"]["standards"]["7.9(D)"]["weak"] is True


def test_group_by_standard_is_the_grouping_shape(tmp_path):
    paths = _Paths(tmp_path)
    _snapshot(paths, "fall", ["7.9(D)", "7.2(B)"], [
        {"n": "Student_001", "pct": 50.0, "missed": {"7.9(D)": 20.0}},
        {"n": "Student_002", "pct": 60.0, "missed": {"7.9(D)": 30.0}},
        {"n": "Student_003", "pct": 95.0, "missed": {"7.2(B)": 10.0}},
    ], "2026-09-01")

    groups = profile_export.group_by_standard(profile_export.build_profile(paths))
    assert groups["7.9(D)"] == ["Student_001", "Student_002"]
    assert groups["7.2(B)"] == ["Student_003"]
    assert list(groups) == ["7.9(D)", "7.2(B)"], "largest need first"


def test_profile_contains_no_real_identities(tmp_path, learning_standard_path, vault_identity):
    """The whole point of the split: this artifact can travel, the vault cannot.

    Driven through the Identity Vault provider, which is what production uses.
    The synthetic workbook's one student is enrolled in the vault, so the run
    has a real pseudonym to substitute rather than trivially dropping identity.
    """
    paths = _Paths(tmp_path)
    provider = vault_identity(("Test Student 1", "1001", "Sparky McGee"))
    parser, _ = pick_parser(learning_standard_path)
    data = parser.parse()
    data.metadata["_anonymizer"] = provider
    data.metadata["_strip_demographics"] = True
    students = json.loads(convert_to_json(data))["students"]
    assert [entry["n"] for entry in students] == ["Sparky McGee"], (
        "the vault pseudonym must reach the snapshot, or this test proves nothing"
    )
    history_store.save_snapshot(paths, {
        "descriptive": "test", "assessment_name": "Test", "grade": "7",
        "type": "STAAR", "breakdown_type": "learning_standard",
        "standards": [{"code": c} for c in data.metadata["standards"]],
        "tier_students": students,
    })

    blob = json.dumps(profile_export.build_profile(paths))
    for student in data.students:
        assert student.student_name not in blob
        assert student.local_id not in blob
