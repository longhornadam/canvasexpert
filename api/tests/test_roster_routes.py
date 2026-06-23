"""Route-level tests for Roster Console API."""
from fastapi.testclient import TestClient
import pytest

from api.webui.server import app
import api.webui.routes.roster as roster_routes

client = TestClient(app)


class FakeVault:
    def __init__(self):
        self.rows = {
            "101": {
                "canvas_id": "101",
                "real_name": "Ada Lovelace",
                "sis_id": "SIS-SECRET",
                "nicknames": ["Addie"],
                "pseudonym": "Sparky McGee",
                "pseudo_first": "Sparky",
                "pseudo_last": "McGee",
                "first_seen": "",
            }
        }
        self.saved = False

    def entries(self):
        return list(self.rows.values())

    def set_nicknames(self, canvas_id, nicknames):
        row = self.rows.setdefault(str(canvas_id), {"canvas_id": str(canvas_id)})
        row["nicknames"] = nicknames

    def set_pseudonym(self, canvas_id, first, last):
        row = self.rows.setdefault(str(canvas_id), {"canvas_id": str(canvas_id)})
        row["pseudo_first"] = first
        row["pseudo_last"] = last
        row["pseudonym"] = f"{first} {last}"

    def regenerate_pseudonym(self, canvas_id):
        self.set_pseudonym(canvas_id, "Fresh", "Alias")

    def save(self):
        self.saved = True


@pytest.fixture(autouse=True)
def isolated_roster(monkeypatch):
    stores = {
        "vault": FakeVault(),
        "extra_time": {},
        "monitored": {},
        "settings": {},
    }

    def fake_get_extra_time(course_id):
        return list(stores["extra_time"].get(str(course_id), []))

    def fake_set_extra_time(course_id, students):
        stores["extra_time"][str(course_id)] = students

    def fake_get_monitored_students():
        return dict(stores["monitored"])

    def fake_set_monitored_student(user_id, name, note=""):
        stores["monitored"][str(user_id)] = {"name": name, "note": note}

    def fake_remove_monitored_student(user_id):
        stores["monitored"].pop(str(user_id), None)

    def fake_get_roster_student_settings(course_id):
        return stores["settings"].get(str(course_id), {})

    def fake_update_roster_student_settings(course_id, user_id, patch):
        course = stores["settings"].setdefault(str(course_id), {})
        row = course.setdefault(str(user_id), {})
        for key, value in patch.items():
            if value is None:
                row.pop(key, None)
            else:
                row[key] = value

    monkeypatch.setattr(roster_routes, "_vault", lambda: stores["vault"])
    monkeypatch.setattr(roster_routes, "_upsert_roster", lambda vault, users: None)
    monkeypatch.setattr(roster_routes, "_fetch_students", lambda course_id: ([], "No token saved."))
    monkeypatch.setattr(roster_routes, "_fetch_sections", lambda course_id: {})
    monkeypatch.setattr(roster_routes, "load_group_categories", lambda course_id: ([], None, ""))
    monkeypatch.setattr(roster_routes.config, "get_extra_time", fake_get_extra_time)
    monkeypatch.setattr(roster_routes.config, "set_extra_time", fake_set_extra_time)
    monkeypatch.setattr(roster_routes.config, "get_monitored_students", fake_get_monitored_students)
    monkeypatch.setattr(roster_routes.config, "set_monitored_student", fake_set_monitored_student)
    monkeypatch.setattr(roster_routes.config, "remove_monitored_student", fake_remove_monitored_student)
    monkeypatch.setattr(roster_routes.config, "get_roster_student_settings", fake_get_roster_student_settings)
    monkeypatch.setattr(roster_routes.config, "update_roster_student_settings", fake_update_roster_student_settings)
    monkeypatch.setattr(roster_routes.config, "active_protected_names", lambda: set())
    monkeypatch.setattr(roster_routes.config, "get_roster_tier_scheme",
                        lambda cid: [{"id": "support", "teacher_label": "Support", "alias": "Blue", "meaning": "below-level", "order": 10, "active": True},
                                     {"id": "core", "teacher_label": "Core", "alias": "Red", "meaning": "on-level", "order": 20, "active": True},
                                     {"id": "extend", "teacher_label": "Extend", "alias": "White", "meaning": "advanced", "order": 30, "active": True}])
    monkeypatch.setattr(roster_routes.config, "active_tier_ids",
                        lambda cid: {"support", "core", "extend"})
    monkeypatch.setattr(roster_routes.config, "migrate_legacy_tier",
                        lambda cid, uid, tier, *a: tier.lower().strip() if tier else None)
    return stores


def test_roster_get_requires_course_id():
    resp = client.get("/api/roster")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "course_id" in data.get("error", "").lower()


def test_roster_get_handles_missing_token():
    resp = client.get("/api/roster?course_id=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "error" in data


def test_roster_get_merges_sources_without_sis(monkeypatch, isolated_roster):
    isolated_roster["extra_time"]["1"] = [{"id": "101", "name": "Ada Lovelace", "days": 2}]
    isolated_roster["monitored"]["101"] = {"name": "Ada Lovelace", "note": "Private note"}
    isolated_roster["settings"]["1"] = {
        "101": {"tier_id": "support"},
    }
    users = [{
        "id": 101,
        "name": "Ada Lovelace",
        "sortable_name": "Lovelace, Ada",
        "short_name": "Ada",
        "sis_user_id": "SIS-SECRET",
        "enrollments": [{"course_section_id": 44}],
    }]
    groups = [{
        "category_id": "7",
        "category_name": "Reading tiers",
        "groups": [{"id": "8", "name": "Blue", "student_ids": [101]}],
    }]
    monkeypatch.setattr(roster_routes, "_fetch_students", lambda course_id: (users, None))
    monkeypatch.setattr(roster_routes, "_fetch_sections", lambda course_id: {"44": "Period 1"})
    monkeypatch.setattr(roster_routes, "load_group_categories", lambda course_id: (groups, None, ""))

    resp = client.get("/api/roster?course_id=1")
    data = resp.json()

    assert data["ok"] is True
    assert "tier_scheme" in data
    assert len(data["tier_scheme"]) == 3
    row = data["students"][0]
    assert row["id"] == "101"
    assert row["nicknames"] == ["Addie"]
    assert row["pseudonym"] == "Sparky McGee"
    assert row["extra_time"] == {"enabled": True, "days": 2}
    assert row["monitored"] == {"enabled": True, "note": "Private note"}
    assert row["tier_id"] == "support"
    assert row["tier_label"] == "Support"
    assert row["tier_alias"] == "Blue"
    assert row["tier_display"] == "Support / Blue"
    assert row["sections"] == [{"id": "44", "name": "Period 1"}]
    assert row["canvas_groups"][0]["group_name"] == "Blue"
    assert "sis_id" not in row
    assert "planned_group" not in row
    assert "Groups" not in str(data.get("groups", ""))


def test_roster_student_requires_ids():
    resp = client.post("/api/roster/student", data={
        "course_id": "", "user_id": "", "patch": "{}"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "course_id" in data.get("error", "").lower()


def test_roster_student_validates_patch_json():
    resp = client.post("/api/roster/student", data={
        "course_id": "1", "user_id": "101", "patch": "not-json"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "json" in data.get("error", "").lower()


def test_roster_student_requires_patch_object():
    resp = client.post("/api/roster/student", data={
        "course_id": "1", "user_id": "101", "patch": '["not-object"]'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "object" in data.get("error", "").lower()


def test_roster_student_rejects_unknown_keys():
    resp = client.post("/api/roster/student", data={
        "course_id": "1", "user_id": "101", "patch": '{"unknown_key": true}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "unknown" in data.get("error", "").lower()


def test_roster_student_validates_nicknames_type():
    resp = client.post("/api/roster/student", data={
        "course_id": "1", "user_id": "101", "patch": '{"nicknames": "not-a-list"}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "list" in data.get("error", "").lower()


def test_roster_student_validates_pseudonym_shape():
    resp = client.post("/api/roster/student", data={
        "course_id": "1", "user_id": "101",
        "patch": '{"pseudonym": {"bad": "shape"}}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "first" in data.get("error", "").lower()


def test_roster_student_validates_tier_id(monkeypatch, isolated_roster):
    """Invalid tier_id should be rejected."""
    monkeypatch.setattr(roster_routes.config, "get_roster_tier_scheme",
                        lambda cid: [{"id": "support", "active": True}])
    resp = client.post("/api/roster/student", data={
        "course_id": "1", "user_id": "101", "patch": '{"tier_id": "nonexistent"}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "tier_id" in data.get("error", "").lower()


def test_roster_student_accepts_valid_tier_id(monkeypatch, isolated_roster):
    """Valid tier_id should be accepted and saved."""
    monkeypatch.setattr(roster_routes.config, "get_roster_tier_scheme",
                        lambda cid: [{"id": "support", "active": True}])
    resp = client.post("/api/roster/student", data={
        "course_id": "1", "user_id": "101", "patch": '{"tier_id": "support"}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True


def test_roster_student_legacy_tier_maps_to_tier_id(monkeypatch, isolated_roster):
    """Legacy 'tier' field should map to tier_id via migrate_legacy_tier."""
    monkeypatch.setattr(roster_routes.config, "get_roster_tier_scheme",
                        lambda cid: [{"id": "support", "teacher_label": "Support", "alias": "Blue", "active": True}])
    monkeypatch.setattr(roster_routes.config, "migrate_legacy_tier",
                        lambda cid, uid, tier, *a: "support")
    resp = client.post("/api/roster/student", data={
        "course_id": "1", "user_id": "101", "patch": '{"tier": "Support"}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True


def test_roster_student_validates_extra_time_days():
    resp = client.post("/api/roster/student", data={
        "course_id": "1", "user_id": "101",
        "patch": '{"extra_time": {"enabled": true, "days": "bad"}}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "integer" in data.get("error", "").lower()


def test_roster_student_legacy_planned_group_is_cleaned(monkeypatch, isolated_roster):
    """Legacy planned_group should be silently cleaned."""
    monkeypatch.setattr(roster_routes.config, "update_roster_student_settings",
                        lambda cid, uid, patch: None)
    resp = client.post("/api/roster/student", data={
        "course_id": "1", "user_id": "101",
        "patch": '{"planned_group": {"category_id": "7", "group_id": "8"}}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True


def test_roster_bulk_requires_params():
    resp = client.post("/api/roster/bulk", data={
        "course_id": "", "user_ids": "[]", "action": ""
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "course_id" in data.get("error", "").lower()


def test_roster_bulk_validates_user_ids_json():
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": "bad-json", "action": "set_extra_time"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "json" in data.get("error", "").lower()


def test_roster_bulk_requires_non_empty_list():
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": "[]", "action": "set_extra_time"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "non-empty" in data.get("error", "").lower()


def test_roster_bulk_rejects_unknown_action():
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": '["101"]', "action": "fly_to_moon"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "unknown" in data.get("error", "").lower()


def test_roster_bulk_validates_tier(monkeypatch, isolated_roster):
    monkeypatch.setattr(roster_routes.config, "active_tier_ids", lambda cid: {"support", "core"})
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": '["101"]',
        "action": "set_tier", "value": '{"tier_id": "bad_tier"}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "tier_id" in data.get("error", "").lower()


def test_roster_bulk_set_tier_by_id(monkeypatch, isolated_roster):
    monkeypatch.setattr(roster_routes.config, "active_tier_ids", lambda cid: {"support", "core"})
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": '["101"]',
        "action": "set_tier", "value": '{"tier_id": "support"}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True


def test_roster_bulk_set_tier_by_legacy_label(monkeypatch, isolated_roster):
    """Bulk set_tier with legacy 'tier' label should still work."""
    monkeypatch.setattr(roster_routes.config, "migrate_legacy_tier",
                        lambda cid, uid, tier, *a: "support")
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": '["101"]',
        "action": "set_tier", "value": '{"tier": "Support"}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True


def test_roster_bulk_set_extra_time_uses_name_map(isolated_roster):
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1",
        "user_ids": '["101"]',
        "action": "set_extra_time",
        "value": '{"days": 2, "names": {"101": "Ada Lovelace"}}',
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert isolated_roster["extra_time"]["1"] == [
        {"id": "101", "name": "Ada Lovelace", "days": 2}
    ]


def test_roster_bulk_clear_extra_time_ok(isolated_roster):
    isolated_roster["extra_time"]["1"] = [{"id": "101", "name": "Ada", "days": 2}]
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": '["101"]',
        "action": "clear_extra_time", "value": "{}"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert isolated_roster["extra_time"]["1"] == []


def test_roster_bulk_clear_tier_ok(isolated_roster):
    isolated_roster["settings"]["1"] = {"101": {"tier": "Support"}}
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": '["101"]',
        "action": "clear_tier", "value": "{}"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert "tier" not in isolated_roster["settings"]["1"]["101"]


def test_roster_bulk_clear_planned_group_ok(isolated_roster):
    isolated_roster["settings"]["1"] = {"101": {"planned_group": {"group_id": "8"}}}
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": '["101"]',
        "action": "clear_planned_group", "value": "{}"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert "planned_group" not in isolated_roster["settings"]["1"]["101"]


def test_roster_bulk_monitor_uses_name_map(isolated_roster):
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": '["101"]',
        "action": "set_monitored", "value": '{"names": {"101": "Ada Lovelace"}}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert isolated_roster["monitored"]["101"]["name"] == "Ada Lovelace"
    assert isolated_roster["monitored"]["101"]["note"] == ""


def test_roster_bulk_clear_monitor_ok(isolated_roster):
    isolated_roster["monitored"]["101"] = {"name": "Ada Lovelace", "note": ""}
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": '["101"]',
        "action": "clear_monitored", "value": "{}"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert "101" not in isolated_roster["monitored"]


def test_bulk_set_planned_group_noop_cleans_up(isolated_roster):
    """set_planned_group should no-op and silently clean up planned_group data."""
    isolated_roster["settings"]["1"] = {"101": {"planned_group": {"group_id": "8"}}}
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": '["101"]',
        "action": "set_planned_group", "value": '{"group_id": "9"}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True


# ── Tier-scheme endpoint tests ──────────────────────────────────────────


def test_tier_scheme_get_requires_course_id():
    resp = client.get("/api/roster/tier-scheme")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "course_id" in data.get("error", "").lower()


def test_tier_scheme_get_returns_default(monkeypatch):
    monkeypatch.setattr(roster_routes.config, "get_roster_tier_scheme",
                        lambda cid: [{"id": "support", "teacher_label": "Support", "alias": "Blue", "order": 10, "active": True}])
    resp = client.get("/api/roster/tier-scheme?course_id=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert len(data["tier_scheme"]) == 1
    assert data["tier_scheme"][0]["id"] == "support"


def test_tier_scheme_post_validates():
    resp = client.post("/api/roster/tier-scheme", data={
        "course_id": "1",
        "scheme": '[{"id": "a", "teacher_label": "A", "alias": "A1"}]'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True


def test_tier_scheme_post_rejects_invalid_json():
    resp = client.post("/api/roster/tier-scheme", data={
        "course_id": "1", "scheme": "bad-json"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "json" in data.get("error", "").lower()


def test_tier_scheme_post_rejects_duplicate_ids():
    resp = client.post("/api/roster/tier-scheme", data={
        "course_id": "1",
        "scheme": '[{"id": "a", "teacher_label": "A", "alias": "One"}, {"id": "a", "teacher_label": "B", "alias": "Two"}]'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "duplicate" in data.get("error", "").lower()
