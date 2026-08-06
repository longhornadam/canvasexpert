"""Canonical School Calendar service: schema, validation, and mutation.

Uses the explicit ``root`` parameter every function accepts (bypassing
``workspace.workspace_root()`` entirely -- see workspace.py's
``_root_or_workspace``) so these tests need no workspace monkeypatching.
"""
import json
import os

from api.webui import school_calendar as sc


def _root(tmp_path):
    return str(tmp_path)


def _read_document(tmp_path):
    path = os.path.join(str(tmp_path), "Library", "Calendars", "School Calendar.json")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# ── read() / calendar_path() ────────────────────────────────────────────────

def test_read_reports_unconfigured_when_no_file(tmp_path):
    doc, problems = sc.read(_root(tmp_path))
    assert doc is None
    assert problems == ["unconfigured"]


def test_read_reports_invalid_calendar_for_malformed_json(tmp_path):
    calendars = tmp_path / "Library" / "Calendars"
    calendars.mkdir(parents=True)
    (calendars / sc.CALENDAR_FILENAME).write_text("{not json", encoding="utf-8")

    doc, problems = sc.read(_root(tmp_path))
    assert doc is None
    assert problems[0].startswith("could not read")


def test_readiness_is_unconfigured_with_no_document(tmp_path):
    readiness = sc.readiness(root=_root(tmp_path))
    assert readiness["status"] == "unconfigured"


# ── create_school_year ──────────────────────────────────────────────────────

def test_create_school_year_covers_every_date_with_weekends_generated(tmp_path):
    doc, problems = sc.create_school_year(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-23",
        default_schedule_id="ordinary", root=_root(tmp_path))
    assert problems == []
    assert doc["revision"] == 1
    assert len(doc["days"]) == 7  # Aug 17-23 inclusive
    assert doc["days"]["2026-08-17"] == {"kind": "instructional", "schedule_id": "ordinary"}
    # Aug 22-23, 2026 are Saturday/Sunday
    assert doc["days"]["2026-08-22"]["kind"] == "no_school"
    assert doc["days"]["2026-08-22"]["label"] == sc.WEEKEND_LABEL
    assert doc["days"]["2026-08-23"]["kind"] == "no_school"


def test_create_school_year_applies_weekday_and_explicit_no_school_overrides(tmp_path):
    doc, problems = sc.create_school_year(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-21",
        default_schedule_id="ordinary", weekday_schedules={"4": "friday_schedule"},
        no_school_dates=["2026-08-19"], date_labels={"2026-08-19": "Staff Day"},
        root=_root(tmp_path))
    assert problems == []
    assert doc["days"]["2026-08-21"]["schedule_id"] == "friday_schedule"  # Friday
    assert doc["days"]["2026-08-19"] == {"kind": "no_school", "schedule_id": None,
                                         "label": "Staff Day"}


def test_create_school_year_rejects_no_school_and_no_regular_overlap(tmp_path):
    doc, problems = sc.create_school_year(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-18",
        default_schedule_id="ordinary",
        no_school_dates=["2026-08-17"], no_regular_classes_dates=["2026-08-17"],
        root=_root(tmp_path))
    assert doc is None
    assert "both no_school and no_regular_classes" in problems[0]


def test_create_school_year_writes_atomically_and_is_readable_back(tmp_path):
    sc.create_school_year(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-17",
        default_schedule_id="ordinary", root=_root(tmp_path))
    on_disk = _read_document(tmp_path)
    assert on_disk["school_year"] == "2026-27"
    doc, problems = sc.read(_root(tmp_path))
    assert problems == []
    assert doc["revision"] == 1


def test_create_school_year_replacing_an_existing_calendar_never_resets_revision(tmp_path):
    sc.create_school_year(
        school_year="2025-26", coverage_start="2025-08-17", coverage_end="2025-08-17",
        default_schedule_id="ordinary", root=_root(tmp_path))
    doc, problems = sc.create_school_year(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-17",
        default_schedule_id="ordinary", root=_root(tmp_path))
    assert problems == []
    assert doc["revision"] == 2
    assert doc["school_year"] == "2026-27"


# ── parse_document / whole-document validation ──────────────────────────────

def test_parse_document_rejects_unknown_top_level_keys():
    payload = {
        "version": sc.FORMAT_VERSION, "type": sc.DOCUMENT_TYPE, "revision": 1,
        "school_year": "2026-27", "coverage": {"start": "2026-08-17", "end": "2026-08-17"},
        "days": {"2026-08-17": {"kind": "instructional", "schedule_id": "ordinary"}},
        "grading_periods": [], "events": [], "extra": "nope",
    }
    doc, problems = sc.parse_document(payload)
    assert doc is None
    assert any("unknown top-level key" in p for p in problems)


def test_parse_document_requires_a_day_for_every_coverage_date():
    payload = {
        "version": sc.FORMAT_VERSION, "type": sc.DOCUMENT_TYPE, "revision": 1,
        "school_year": "2026-27", "coverage": {"start": "2026-08-17", "end": "2026-08-18"},
        "days": {"2026-08-17": {"kind": "instructional", "schedule_id": "ordinary"}},
        "grading_periods": [], "events": [],
    }
    doc, problems = sc.parse_document(payload)
    assert doc is None
    assert any("missing" in p for p in problems)


def test_parse_document_rejects_instructional_day_without_schedule_id():
    payload = {
        "version": sc.FORMAT_VERSION, "type": sc.DOCUMENT_TYPE, "revision": 1,
        "school_year": "2026-27", "coverage": {"start": "2026-08-17", "end": "2026-08-17"},
        "days": {"2026-08-17": {"kind": "instructional", "schedule_id": None}},
        "grading_periods": [], "events": [],
    }
    doc, problems = sc.parse_document(payload)
    assert doc is None
    assert any("requires a non-empty schedule_id" in p for p in problems)


def test_parse_document_rejects_no_school_day_naming_a_schedule():
    payload = {
        "version": sc.FORMAT_VERSION, "type": sc.DOCUMENT_TYPE, "revision": 1,
        "school_year": "2026-27", "coverage": {"start": "2026-08-17", "end": "2026-08-17"},
        "days": {"2026-08-17": {"kind": "no_school", "schedule_id": "ordinary", "label": "Break"}},
        "grading_periods": [], "events": [],
    }
    doc, problems = sc.parse_document(payload)
    assert doc is None
    assert any("must not name a schedule_id" in p for p in problems)


def test_parse_document_rejects_overlapping_grading_periods():
    payload = {
        "version": sc.FORMAT_VERSION, "type": sc.DOCUMENT_TYPE, "revision": 1,
        "school_year": "2026-27", "coverage": {"start": "2026-08-01", "end": "2026-08-31"},
        "days": {}, "grading_periods": [
            {"code": "T1", "name": "Term 1", "start": "2026-08-01", "end": "2026-08-20"},
            {"code": "T2", "name": "Term 2", "start": "2026-08-15", "end": "2026-08-31"},
        ], "events": [],
    }
    doc, problems = sc.parse_document(payload)
    assert doc is None
    assert any("overlap" in p for p in problems)


def test_parse_document_rejects_ambiguous_event_id_and_kind():
    payload = {
        "version": sc.FORMAT_VERSION, "type": sc.DOCUMENT_TYPE, "revision": 1,
        "school_year": "2026-27", "coverage": {"start": "2026-08-01", "end": "2026-08-01"},
        "days": {}, "grading_periods": [], "events": [
            {"id": "e1", "kind": "ssn", "label": "Bad", "shape": "date", "date": "2026-08-01"},
        ],
    }
    doc, problems = sc.parse_document(payload)
    assert doc is None
    assert any("kind must be one of" in p for p in problems)


# ── resolve_date ─────────────────────────────────────────────────────────────

def test_resolve_date_unconfigured_when_no_document():
    resolution = sc.resolve_date(None, "2026-08-17", set())
    assert resolution["state"] == "unconfigured"


def test_resolve_date_outside_coverage(tmp_path):
    doc, _ = sc.create_school_year(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-17",
        default_schedule_id="ordinary", root=_root(tmp_path))
    resolution = sc.resolve_date(doc, "2026-09-01", set())
    assert resolution["state"] == "outside_coverage"


def test_resolve_date_unknown_schedule_when_bell_schedule_missing(tmp_path):
    doc, _ = sc.create_school_year(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-17",
        default_schedule_id="ordinary", root=_root(tmp_path))
    resolution = sc.resolve_date(doc, "2026-08-17", known_schedule_ids=set())
    assert resolution["state"] == "unknown_schedule"


def test_resolve_date_ready_when_schedule_known(tmp_path):
    doc, _ = sc.create_school_year(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-17",
        default_schedule_id="ordinary", root=_root(tmp_path))
    resolution = sc.resolve_date(doc, "2026-08-17", known_schedule_ids={"ordinary"})
    assert resolution == {"state": "ready", "date": "2026-08-17",
                          "schedule_id": "ordinary", "label": None}


def test_resolve_date_no_school_and_no_regular_classes(tmp_path):
    doc, _ = sc.create_school_year(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-18",
        default_schedule_id="ordinary",
        no_school_dates=["2026-08-17"], no_regular_classes_dates=["2026-08-18"],
        root=_root(tmp_path))
    assert sc.resolve_date(doc, "2026-08-17", set())["state"] == "no_school"
    assert sc.resolve_date(doc, "2026-08-18", set())["state"] == "no_regular_classes"


# ── resolve_instructional_range / add_school_days_checked / count_school_days_checked ──

def test_resolve_instructional_range_fails_closed_when_unconfigured(tmp_path):
    result = sc.resolve_instructional_range(
        "2026-08-17", "2026-08-20", set(), root=_root(tmp_path))
    assert result["state"] == "unconfigured"
    assert result["repair_url"] == "/calendar"


def test_resolve_instructional_range_reports_no_count_dates_in_range(tmp_path):
    sc.create_school_year(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-23",
        default_schedule_id="ordinary", no_school_dates=["2026-08-19"],
        root=_root(tmp_path))
    result = sc.resolve_instructional_range(
        "2026-08-17", "2026-08-23", {"ordinary"}, root=_root(tmp_path))
    assert result["state"] == "ready"
    assert set(result["no_count_dates"]) == {"2026-08-19", "2026-08-22", "2026-08-23"}


def test_resolve_instructional_range_refuses_partial_coverage_rather_than_clipping(tmp_path):
    sc.create_school_year(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-23",
        default_schedule_id="ordinary", root=_root(tmp_path))
    result = sc.resolve_instructional_range(
        "2026-08-20", "2026-09-01", {"ordinary"}, root=_root(tmp_path))
    assert result["state"] == "outside_coverage"


def test_resolve_instructional_range_reports_unknown_schedule(tmp_path):
    sc.create_school_year(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-18",
        default_schedule_id="ordinary", root=_root(tmp_path))
    result = sc.resolve_instructional_range(
        "2026-08-17", "2026-08-18", set(), root=_root(tmp_path))
    assert result["state"] == "unknown_schedule"


def test_add_school_days_checked_advances_past_weekends_and_no_school_days(tmp_path):
    from datetime import datetime
    sc.create_school_year(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-25",
        default_schedule_id="ordinary", no_school_dates=["2026-08-20"],
        root=_root(tmp_path))
    start = datetime(2026, 8, 19)  # Wednesday
    result, failure = sc.add_school_days_checked(start, 2, {"ordinary"}, root=_root(tmp_path))
    assert failure is None
    # Aug 20 is no-school, Aug 21 (Fri) and Aug 24 (Mon) are the next two school days.
    assert result.date().isoformat() == "2026-08-24"


def test_add_school_days_checked_refuses_rather_than_walking_past_coverage(tmp_path):
    from datetime import datetime
    sc.create_school_year(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-21",
        default_schedule_id="ordinary", root=_root(tmp_path))
    start = datetime(2026, 8, 21)  # coverage's final Friday
    result, failure = sc.add_school_days_checked(start, 1, {"ordinary"}, root=_root(tmp_path))
    assert result is None
    assert failure["state"] == "outside_coverage"


def test_count_school_days_checked_excludes_no_count_dates(tmp_path):
    from datetime import datetime
    sc.create_school_year(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-25",
        default_schedule_id="ordinary", root=_root(tmp_path))
    due = datetime(2026, 8, 19)  # Wednesday
    submitted = datetime(2026, 8, 24)  # following Monday
    count, failure = sc.count_school_days_checked(due, submitted, {"ordinary"}, root=_root(tmp_path))
    assert failure is None
    assert count == 3  # Thu, Fri, Mon -- weekend excluded


def test_count_school_days_checked_reports_unknown_schedule(tmp_path):
    from datetime import datetime
    sc.create_school_year(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-25",
        default_schedule_id="ordinary", root=_root(tmp_path))
    due = datetime(2026, 8, 19)
    submitted = datetime(2026, 8, 21)
    count, failure = sc.count_school_days_checked(due, submitted, set(), root=_root(tmp_path))
    assert count is None
    assert failure["state"] == "unknown_schedule"


# ── preview_change / apply_change ───────────────────────────────────────────

def _seeded(tmp_path, **kwargs):
    defaults = dict(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-28",
        default_schedule_id="ordinary", root=_root(tmp_path))
    defaults.update(kwargs)
    doc, problems = sc.create_school_year(**defaults)
    assert problems == []
    return doc


def test_preview_change_reports_affected_dates_and_base_revision(tmp_path):
    _seeded(tmp_path)
    preview, problems = sc.preview_change(
        kind="no_school", label="Field day", dates=["2026-08-18"],
        known_schedule_ids=set(), root=_root(tmp_path))
    assert problems == []
    assert preview["base_revision"] == 1
    assert preview["is_noop"] is False
    assert preview["operation"] == "date_change"
    assert preview["conflicts"] == [{
        "date": "2026-08-18", "reason": "kind_change",
        "from_kind": "instructional", "from_label": None,
        "to_kind": "no_school",
    }]
    assert preview["affected"] == [{
        "date": "2026-08-18",
        "before": {"kind": "instructional", "schedule_id": "ordinary"},
        "after": {"kind": "no_school", "schedule_id": None, "label": "Field day"},
    }]


def test_preview_change_rejects_an_unknown_schedule_id(tmp_path):
    _seeded(tmp_path)
    preview, problems = sc.preview_change(
        kind="instructional", schedule_id="friday_schedule", dates=["2026-08-21"],
        known_schedule_ids=set(), root=_root(tmp_path))
    assert preview is None
    assert "not a currently loaded Bell Schedule" in problems[0]


def test_preview_change_range_with_weekday_subset(tmp_path):
    _seeded(tmp_path)
    preview, problems = sc.preview_change(
        kind="instructional", schedule_id="friday_schedule",
        date_from="2026-08-17", date_to="2026-08-28", weekdays=[4],
        known_schedule_ids={"friday_schedule"}, root=_root(tmp_path))
    assert problems == []
    dates = [entry["date"] for entry in preview["affected"]]
    assert dates == ["2026-08-21", "2026-08-28"]  # the two Fridays in range


def test_preview_change_warns_on_holiday_and_apply_preserves_label(tmp_path):
    _seeded(tmp_path, no_school_dates=["2026-08-19"],
            date_labels={"2026-08-19": "Staff Development"})
    preview, problems = sc.preview_change(
        kind="instructional", schedule_id="friday_schedule",
        dates=["2026-08-19"], known_schedule_ids={"friday_schedule"}, root=_root(tmp_path))

    assert problems == []
    assert preview["conflicts"] == [{
        "date": "2026-08-19", "reason": "kind_change",
        "from_kind": "no_school", "from_label": "Staff Development",
        "to_kind": "instructional",
    }]
    altered_projection = dict(preview, conflicts=[{"date": "2026-08-19", "reason": "reviewed"}])
    applied, problems = sc.apply_change(
        altered_projection, expected_revision=preview["base_revision"], root=_root(tmp_path))
    assert problems == []
    assert applied["days"]["2026-08-19"] == {
        "kind": "instructional", "schedule_id": "friday_schedule",
        "label": "Staff Development",
    }


def test_preview_change_without_weekdays_warns_on_weekends(tmp_path):
    _seeded(tmp_path, coverage_start="2026-08-17", coverage_end="2026-08-24")
    preview, problems = sc.preview_change(
        kind="instructional", schedule_id="friday_schedule",
        date_from="2026-08-17", date_to="2026-08-24",
        known_schedule_ids={"friday_schedule"}, root=_root(tmp_path))

    assert problems == []
    assert preview["conflicts"] == [
        {"date": "2026-08-22", "reason": "weekend", "from_kind": "no_school",
         "from_label": "Weekend", "to_kind": "instructional"},
        {"date": "2026-08-23", "reason": "weekend", "from_kind": "no_school",
         "from_label": "Weekend", "to_kind": "instructional"},
    ]


def test_instructional_label_is_preserved_without_one_and_replaced_when_supplied(tmp_path):
    _seeded(tmp_path)
    path = tmp_path / "Library" / "Calendars" / "School Calendar.json"
    document = _read_document(tmp_path)
    document["days"]["2026-08-17"]["label"] = "Early release"
    path.write_text(json.dumps(document), encoding="utf-8")

    preserve_preview, problems = sc.preview_change(
        kind="instructional", schedule_id="friday_schedule", dates=["2026-08-17"],
        known_schedule_ids={"friday_schedule"}, root=_root(tmp_path))
    assert problems == []
    assert preserve_preview["mutation"]["entries"] == {
        "2026-08-17": {"kind": "instructional", "schedule_id": "friday_schedule",
                        "label": "Early release"},
    }
    applied, problems = sc.apply_change(
        preserve_preview, expected_revision=1, root=_root(tmp_path))
    assert problems == []
    assert applied["days"]["2026-08-17"]["label"] == "Early release"

    replace_preview, problems = sc.preview_change(
        kind="instructional", schedule_id="friday_schedule", label="First day",
        dates=["2026-08-18"], known_schedule_ids={"friday_schedule"}, root=_root(tmp_path))
    assert problems == []
    assert replace_preview["affected"][0]["after"] == {
        "kind": "instructional", "schedule_id": "friday_schedule", "label": "First day",
    }
    applied, problems = sc.apply_change(
        replace_preview, expected_revision=2, root=_root(tmp_path))
    assert problems == []
    assert applied["days"]["2026-08-18"]["label"] == "First day"


def test_preview_change_refuses_both_dates_and_range(tmp_path):
    _seeded(tmp_path)
    preview, problems = sc.preview_change(
        kind="no_school", label="X", dates=["2026-08-18"],
        date_from="2026-08-17", date_to="2026-08-18",
        known_schedule_ids=set(), root=_root(tmp_path))
    assert preview is None
    assert "either an explicit date list or a date range" in problems[0]


def test_preview_change_rejects_dates_outside_coverage(tmp_path):
    _seeded(tmp_path)
    preview, problems = sc.preview_change(
        kind="no_school", label="X", dates=["2026-09-01"],
        known_schedule_ids=set(), root=_root(tmp_path))
    assert preview is None
    assert "outside coverage" in problems[0]


def test_preview_change_is_noop_when_nothing_would_change(tmp_path):
    _seeded(tmp_path)
    preview, problems = sc.preview_change(
        kind="instructional", schedule_id="ordinary", dates=["2026-08-17"],
        known_schedule_ids={"ordinary"}, root=_root(tmp_path))
    assert problems == []
    assert preview["is_noop"] is True


def test_apply_change_writes_and_increments_revision(tmp_path):
    _seeded(tmp_path)
    preview, _ = sc.preview_change(
        kind="no_school", label="Field day", dates=["2026-08-18"],
        known_schedule_ids=set(), root=_root(tmp_path))
    doc, problems = sc.apply_change(preview, expected_revision=1, root=_root(tmp_path))
    assert problems == []
    assert doc["revision"] == 2
    assert doc["days"]["2026-08-18"] == {"kind": "no_school", "schedule_id": None,
                                         "label": "Field day"}


def test_apply_change_noop_does_not_increment_revision(tmp_path):
    _seeded(tmp_path)
    preview, _ = sc.preview_change(
        kind="instructional", schedule_id="ordinary", dates=["2026-08-17"],
        known_schedule_ids={"ordinary"}, root=_root(tmp_path))
    doc, problems = sc.apply_change(preview, expected_revision=1, root=_root(tmp_path))
    assert problems == []
    assert doc["revision"] == 1


def test_apply_change_refuses_a_stale_revision(tmp_path):
    _seeded(tmp_path)
    preview, _ = sc.preview_change(
        kind="no_school", label="Field day", dates=["2026-08-18"],
        known_schedule_ids=set(), root=_root(tmp_path))
    # Someone else applies a change first, advancing the real revision to 2.
    other_preview, _ = sc.preview_change(
        kind="no_school", label="Other", dates=["2026-08-19"],
        known_schedule_ids=set(), root=_root(tmp_path))
    sc.apply_change(other_preview, expected_revision=1, root=_root(tmp_path))

    doc, problems = sc.apply_change(preview, expected_revision=1, root=_root(tmp_path))
    assert doc is None
    assert "stale revision" in problems[0]
    # The stale apply must not have overwritten the real revision-2 write.
    current, _ = sc.read(_root(tmp_path))
    assert current["revision"] == 2
    assert current["days"]["2026-08-19"]["kind"] == "no_school"
    assert current["days"]["2026-08-18"]["kind"] == "instructional"


def test_apply_change_refuses_an_altered_mutation_via_digest_mismatch(tmp_path):
    _seeded(tmp_path)
    preview, _ = sc.preview_change(
        kind="no_school", label="Field day", dates=["2026-08-18"],
        known_schedule_ids=set(), root=_root(tmp_path))
    tampered = dict(preview)
    tampered["mutation"] = dict(preview["mutation"], dates=["2026-08-19"])
    doc, problems = sc.apply_change(tampered, expected_revision=1, root=_root(tmp_path))
    assert doc is None
    assert "digest mismatch" in problems[0]


def test_apply_change_requires_a_valid_preview_object(tmp_path):
    _seeded(tmp_path)
    doc, problems = sc.apply_change({"not": "a preview"}, expected_revision=1, root=_root(tmp_path))
    assert doc is None
    assert "valid preview is required" in problems[0]


def test_game_result_is_valid_and_restricted_to_games():
    base = {
        "version": sc.FORMAT_VERSION, "type": sc.DOCUMENT_TYPE, "revision": 1,
        "school_year": "2026-27", "coverage": {"start": "2026-08-17", "end": "2026-08-17"},
        "days": {"2026-08-17": {"kind": "instructional", "schedule_id": "ordinary"}},
        "grading_periods": [],
    }
    valid, problems = sc.parse_document({**base, "events": [{
        "id": "game-1", "kind": "game", "label": "Bobcats", "shape": "date",
        "date": "2026-08-17", "result": "Won 2-1",
    }]})
    assert problems == []
    assert valid["events"][0]["result"] == "Won 2-1"
    for event in [
        {"id": "other", "kind": "other", "label": "No", "shape": "date",
         "date": "2026-08-17", "result": ""},
        {"id": "game-2", "kind": "game", "label": "No", "shape": "date",
         "date": "2026-08-17", "result": 2},
        {"id": "game-3", "kind": "game", "label": "No", "shape": "date",
         "date": "2026-08-17", "result": "x" * 161},
    ]:
        parsed, problems = sc.parse_document({**base, "events": [event]})
        assert parsed is None
        assert problems


def test_event_clock_values_are_12_hour_and_normalized():
    event = {
        "id": "concert", "kind": "performance", "label": "Concert",
        "shape": "date", "date": "2026-08-17",
        "from": "6:30 pm", "to": "8:00 PM",
    }
    normalized, problems = sc._normalize_event(event)
    assert problems == []
    assert normalized["from"] == "6:30 PM"
    assert normalized["to"] == "8:00 PM"

    # From/To are free-text inputs, so a two-digit-hour 24-hour value is accepted
    # and stored in the canonical 12-hour form rather than refused for spelling.
    normalized, problems = sc._normalize_event({**event, "from": "18:30"})
    assert problems == []
    assert normalized["from"] == "6:30 PM"

    # Tolerance stops at ambiguity: "1:15" would resolve to the middle of the
    # night, so it stays a reported problem instead of a silent wrong time.
    for value in ("1:15", "25:00", "half six"):
        normalized, problems = sc._normalize_event({**event, "from": value})
        assert normalized is None, value
        assert "time like '6:30 PM'" in problems[0]


def test_event_change_add_replace_delete_noop_and_projection_tamper(tmp_path):
    _seeded(tmp_path)
    event = {"id": "game-1", "kind": "game", "label": "Bobcats", "shape": "date",
             "date": "2026-08-18", "result": "Won 2-1"}
    preview, problems = sc.preview_event_change(
        action="upsert", event=event, root=_root(tmp_path))
    assert problems == []
    assert preview["operation"] == "event_change"
    assert preview["before"] is None and preview["after"] == event
    doc, problems = sc.apply_event_change(preview, expected_revision=1, root=_root(tmp_path))
    assert problems == [] and doc["revision"] == 2

    replacement = {**event, "result": "Lost 1-2"}
    preview, problems = sc.preview_event_change(
        action="upsert", event=replacement, root=_root(tmp_path))
    assert problems == []
    tampered = {**preview, "before": {"id": "wrong"}}
    doc, problems = sc.apply_event_change(tampered, expected_revision=2, root=_root(tmp_path))
    assert doc is None and "projection mismatch" in problems[0]
    doc, problems = sc.apply_event_change(preview, expected_revision=2, root=_root(tmp_path))
    assert problems == [] and doc["revision"] == 3

    preview, problems = sc.preview_event_change(
        action="delete", event_id="game-1", root=_root(tmp_path))
    doc, problems = sc.apply_event_change(preview, expected_revision=3, root=_root(tmp_path))
    assert problems == [] and doc["revision"] == 4 and doc["events"] == []
    preview, problems = sc.preview_event_change(
        action="delete", event_id="missing", root=_root(tmp_path))
    doc, problems = sc.apply_event_change(preview, expected_revision=4, root=_root(tmp_path))
    assert problems == [] and doc["revision"] == 4


# ── preview_replacement / apply_replacement ─────────────────────────────────

def test_preview_replacement_is_create_at_base_revision_zero_when_unconfigured(tmp_path):
    preview, problems = sc.preview_replacement(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-18",
        default_schedule_id="ordinary", known_schedule_ids={"ordinary"}, root=_root(tmp_path))
    assert problems == []
    assert preview["operation"] == "create"
    assert preview["base_revision"] == 0
    assert preview["current_school_year"] is None
    assert preview["day_count"] == 2


def test_apply_replacement_writes_revision_1_on_first_create(tmp_path):
    preview, _ = sc.preview_replacement(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-18",
        default_schedule_id="ordinary", known_schedule_ids={"ordinary"}, root=_root(tmp_path))
    doc, problems = sc.apply_replacement(preview, expected_revision=0, root=_root(tmp_path))
    assert problems == []
    assert doc["revision"] == 1


def test_preview_replacement_is_replace_at_current_revision_when_already_configured(tmp_path):
    _seeded(tmp_path)
    preview, problems = sc.preview_replacement(
        school_year="2027-28", coverage_start="2027-08-16", coverage_end="2027-08-17",
        default_schedule_id="ordinary", known_schedule_ids={"ordinary"}, root=_root(tmp_path))
    assert problems == []
    assert preview["operation"] == "replace"
    assert preview["base_revision"] == 1
    assert preview["current_school_year"] == "2026-27"


def test_apply_replacement_never_resets_revision_on_replace(tmp_path):
    _seeded(tmp_path)  # revision 1
    preview, _ = sc.preview_replacement(
        school_year="2027-28", coverage_start="2027-08-16", coverage_end="2027-08-17",
        default_schedule_id="ordinary", known_schedule_ids={"ordinary"}, root=_root(tmp_path))
    doc, problems = sc.apply_replacement(preview, expected_revision=1, root=_root(tmp_path))
    assert problems == []
    assert doc["revision"] == 2
    assert doc["school_year"] == "2027-28"


def test_apply_replacement_refuses_a_stale_preview(tmp_path):
    _seeded(tmp_path)  # revision 1
    preview, _ = sc.preview_replacement(
        school_year="2027-28", coverage_start="2027-08-16", coverage_end="2027-08-17",
        default_schedule_id="ordinary", known_schedule_ids={"ordinary"}, root=_root(tmp_path))
    # Someone else replaces first, advancing the real revision to 2.
    other_preview, _ = sc.preview_replacement(
        school_year="2028-29", coverage_start="2028-08-14", coverage_end="2028-08-15",
        default_schedule_id="ordinary", known_schedule_ids={"ordinary"}, root=_root(tmp_path))
    sc.apply_replacement(other_preview, expected_revision=1, root=_root(tmp_path))

    doc, problems = sc.apply_replacement(preview, expected_revision=1, root=_root(tmp_path))
    assert doc is None
    assert "stale revision" in problems[0]
    current, _ = sc.read(_root(tmp_path))
    assert current["revision"] == 2
    assert current["school_year"] == "2028-29"


def test_preview_replacement_rejects_an_unknown_bell_schedule(tmp_path):
    preview, problems = sc.preview_replacement(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-18",
        default_schedule_id="ordinary", known_schedule_ids=set(), root=_root(tmp_path))
    assert preview is None
    assert "not currently loaded" in problems[0]


def test_apply_replacement_refuses_an_altered_mutation_via_digest_mismatch(tmp_path):
    preview, _ = sc.preview_replacement(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-18",
        default_schedule_id="ordinary", known_schedule_ids={"ordinary"}, root=_root(tmp_path))
    tampered = dict(preview)
    tampered["mutation"] = dict(preview["mutation"], school_year="2099-00")
    doc, problems = sc.apply_replacement(tampered, expected_revision=0, root=_root(tmp_path))
    assert doc is None
    assert "digest mismatch" in problems[0]


# ── range_projection ─────────────────────────────────────────────────────────

def test_range_projection_returns_days_periods_and_events_in_range(tmp_path):
    sc.create_school_year(
        school_year="2026-27", coverage_start="2026-08-01", coverage_end="2026-08-31",
        default_schedule_id="ordinary",
        grading_periods=[{"code": "T1", "name": "Term 1",
                          "start": "2026-08-01", "end": "2026-08-31"}],
        events=[{"id": "concert", "kind": "performance", "label": "Fall Concert",
                 "shape": "date", "date": "2026-08-15"}],
        root=_root(tmp_path))
    projection, problems = sc.range_projection("2026-08-10", "2026-08-20", root=_root(tmp_path))
    assert problems == []
    assert set(projection["days"]) == {
        f"2026-08-{day:02d}" for day in range(10, 21)
    }
    assert projection["grading_periods"][0]["code"] == "T1"
    assert projection["events"][0]["label"] == "Fall Concert"


def test_range_projection_unconfigured_returns_none(tmp_path):
    projection, problems = sc.range_projection("2026-08-10", "2026-08-20", root=_root(tmp_path))
    assert projection is None
    assert problems == ["unconfigured"]
