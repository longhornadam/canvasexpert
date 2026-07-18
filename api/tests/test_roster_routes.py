"""Route-level tests for Roster Console API (V3: Canvas groups are source of truth)."""
import json
from fastapi.testclient import TestClient
from contextlib import contextmanager
import pytest

from api.webui.server import app
import api.webui.routes.roster as roster_routes
from api.mirror import store as mirror_store

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

    @contextmanager
    def transaction(self):
        yield self

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

    def fake_get_roster_group_scheme(course_id):
        return stores.get("group_schemes", {}).get(str(course_id), {})

    def fake_set_roster_group_scheme(course_id, scheme):
        stores.setdefault("group_schemes", {})[str(course_id)] = scheme

    def fake_get_selected_group_category_id(course_id):
        return fake_get_roster_group_scheme(course_id).get("selected_group_category_id")

    def fake_set_selected_group_category_id(course_id, cat_id):
        scheme = fake_get_roster_group_scheme(course_id)
        scheme["selected_group_category_id"] = cat_id
        fake_set_roster_group_scheme(course_id, scheme)

    def fake_get_group_label(course_id, group_id):
        scheme = fake_get_roster_group_scheme(course_id)
        return scheme.get("group_labels", {}).get(str(group_id))

    def fake_set_group_label(course_id, group_id, teacher_label, meaning=""):
        scheme = fake_get_roster_group_scheme(course_id)
        labels = scheme.setdefault("group_labels", {})
        labels[str(group_id)] = {"teacher_label": teacher_label, "meaning": meaning}
        fake_set_roster_group_scheme(course_id, scheme)

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
    monkeypatch.setattr(roster_routes.config, "get_roster_group_scheme", fake_get_roster_group_scheme)
    monkeypatch.setattr(roster_routes.config, "set_roster_group_scheme", fake_set_roster_group_scheme)
    monkeypatch.setattr(roster_routes.config, "get_selected_group_category_id", fake_get_selected_group_category_id)
    monkeypatch.setattr(roster_routes.config, "set_selected_group_category_id", fake_set_selected_group_category_id)
    monkeypatch.setattr(roster_routes.config, "get_group_label", fake_get_group_label)
    monkeypatch.setattr(roster_routes.config, "set_group_label", fake_set_group_label)
    monkeypatch.setattr(roster_routes.config, "compute_group_display",
                        lambda label, name: f"{label} / {name}" if label and label != name else name)
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
    assert data.get("ok") is False
    assert "error" in data


def test_roster_get_merges_sources_without_sis(monkeypatch, isolated_roster):
    isolated_roster["extra_time"]["1"] = [{"id": "101", "name": "Ada Lovelace", "days": 2}]
    isolated_roster["monitored"]["101"] = {"name": "Ada Lovelace", "note": "Private note"}
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
    # V3: groups and group_label_scheme instead of tier_scheme
    assert "groups" in data
    assert "group_label_scheme" in data
    row = data["students"][0]
    assert row["id"] == "101"
    assert row["nicknames"] == ["Addie"]
    assert row["pseudonym"] == "Sparky McGee"
    assert row["extra_time"] == {"enabled": True, "days": 2}
    assert row["monitored"] == {"enabled": True, "note": "Private note"}
    # V3: canvas_group instead of tier_id
    assert "canvas_group" in row
    assert row["canvas_groups"][0]["group_name"] == "Blue"
    assert "sis_id" not in row
    assert "Groups" not in str(data.get("groups", ""))


def test_roster_get_uses_current_mirror_before_live_students_and_sections(
    monkeypatch, isolated_roster,
):
    roster_document = {
        "state": "current",
        "students": {
            "101": {
                "id": "101",
                "name": "Ada Lovelace",
                "sortable_name": "Lovelace, Ada",
                "short_name": "Ada",
                "sis_user_id": "SIS-SECRET",
                "enrollments": [{"course_section_id": "44"}],
            }
        },
        "sections": {"44": "Period 1"},
    }
    group_calls = []

    monkeypatch.setattr(roster_routes.mirror_store, "read_roster",
                        lambda course_id: roster_document)
    monkeypatch.setattr(roster_routes, "_fetch_students",
                        lambda course_id: pytest.fail("students must use the mirror"))
    monkeypatch.setattr(roster_routes, "_fetch_sections",
                        lambda course_id: pytest.fail("sections must use the mirror"))
    monkeypatch.setattr(
        roster_routes,
        "load_group_categories",
        lambda course_id: (group_calls.append(course_id) or [], None, ""),
    )

    data = client.get("/api/roster?course_id=1").json()

    assert data["ok"] is True
    assert data["students"][0]["id"] == "101"
    assert data["students"][0]["sections"] == [{"id": "44", "name": "Period 1"}]
    assert "sis_id" not in data["students"][0]
    assert group_calls == ["1"]


def _current_roster_document():
    return {
        "state": "current",
        "students": {
            "101": {
                "id": "101", "name": "Ada Lovelace", "sortable_name": "Lovelace, Ada",
                "short_name": "Ada", "sis_user_id": "", "enrollments": [],
            }
        },
        "sections": {},
    }


def _groups_snapshot(state="current"):
    return {
        "state": state,
        "last_success_at": mirror_store.now_iso(),
        "categories": [{
            "category_id": "7", "category_name": "Reading groups",
            "groups": [{"id": "8", "name": "Blue", "memberships": [{"id": "9", "user_id": "101"}]}],
        }],
    }


def test_roster_get_uses_fresh_private_groups_without_live_loader(monkeypatch, isolated_roster):
    monkeypatch.setattr(roster_routes.mirror_store, "read_roster",
                        lambda course_id: _current_roster_document())
    monkeypatch.setattr(roster_routes.mirror_store, "read_groups",
                        lambda course_id: _groups_snapshot())
    monkeypatch.setattr(roster_routes, "load_group_categories",
                        lambda course_id: pytest.fail("fresh group snapshot must avoid the live loader"))

    data = client.get("/api/roster?course_id=1").json()

    assert data["ok"] is True
    assert data["groups"][0]["groups"][0]["student_ids"] == ["101"]
    assert data["students"][0]["canvas_groups"][0]["group_name"] == "Blue"


@pytest.mark.parametrize("snapshot", [None, _groups_snapshot("stale")])
def test_roster_get_falls_back_live_for_missing_or_stale_groups(monkeypatch, isolated_roster, snapshot):
    live_categories = [{
        "category_id": "7", "category_name": "Live groups",
        "groups": [{"id": "8", "name": "Blue", "memberships": [{"id": "9", "user_id": "101"}]}],
    }]
    writes = []
    monkeypatch.setattr(roster_routes.mirror_store, "read_roster",
                        lambda course_id: _current_roster_document())
    monkeypatch.setattr(roster_routes.mirror_store, "read_groups", lambda course_id: snapshot)
    monkeypatch.setattr(roster_routes, "load_group_categories",
                        lambda course_id: (live_categories, None, ""))
    monkeypatch.setattr(roster_routes.mirror_store, "write_groups",
                        lambda course_id, categories: writes.append((course_id, categories)))

    data = client.get("/api/roster?course_id=1").json()

    assert data["ok"] is True
    assert data["groups"][0]["category_name"] == "Live groups"
    assert writes == [("1", live_categories)]


def test_roster_live_group_failure_does_not_replace_snapshot(monkeypatch, isolated_roster):
    monkeypatch.setattr(roster_routes.mirror_store, "read_roster",
                        lambda course_id: _current_roster_document())
    monkeypatch.setattr(roster_routes.mirror_store, "read_groups",
                        lambda course_id: _groups_snapshot("stale"))
    monkeypatch.setattr(roster_routes, "load_group_categories",
                        lambda course_id: ([], "forbidden", ""))
    monkeypatch.setattr(roster_routes.mirror_store, "write_groups",
                        lambda *args: pytest.fail("failed live read must preserve last-good snapshot"))

    data = client.get("/api/roster?course_id=1").json()

    assert data["ok"] is True
    assert data["groups"] == []


def test_private_group_snapshot_round_trip_has_only_allowlisted_fields(tmp_path):
    mirror_store.write_groups("1", [{
        "category_id": 7, "category_name": "Reading groups", "ignored": "not persisted",
        "groups": [{
            "id": 8, "name": "Blue", "other": "not persisted",
            "memberships": [{"id": 9, "user_id": 101, "user_name": "not persisted"}],
        }],
    }], root=tmp_path, attempted_at="2026-07-18T00:00:00Z")

    with open(mirror_store.groups_path("1", root=tmp_path), encoding="utf-8") as handle:
        document = json.load(handle)

    assert set(document) == {
        "schema_version", "course_id", "state", "last_success_at", "last_attempt_at", "error_code", "categories",
    }
    assert document["categories"] == [{
        "category_id": "7", "category_name": "Reading groups",
        "groups": [{"id": "8", "name": "Blue", "memberships": [{"id": "9", "user_id": "101"}]}],
    }]
    stale = mirror_store.invalidate_groups("1", root=tmp_path, attempted_at="2026-07-18T01:00:00Z")
    assert stale["state"] == "stale"
    assert stale["categories"] == document["categories"]
    assert mirror_store.groups_are_current(stale, max_age_hours=24) is False


def test_private_group_snapshot_rejects_ambiguous_duplicate_ids(tmp_path):
    duplicate_category = [
        {"category_id": "7", "category_name": "One", "groups": []},
        {"category_id": "7", "category_name": "Two", "groups": []},
    ]
    duplicate_group = [{
        "category_id": "7", "category_name": "One",
        "groups": [
            {"id": "8", "name": "Blue", "memberships": []},
            {"id": "8", "name": "Green", "memberships": []},
        ],
    }]
    duplicate_membership_id = [{
        "category_id": "7", "category_name": "One",
        "groups": [{
            "id": "8", "name": "Blue",
            "memberships": [{"id": "9", "user_id": "101"}, {"id": "9", "user_id": "102"}],
        }],
    }]
    duplicate_user_id = [{
        "category_id": "7", "category_name": "One",
        "groups": [{
            "id": "8", "name": "Blue",
            "memberships": [{"id": "9", "user_id": "101"}, {"id": "10", "user_id": "101"}],
        }],
    }]

    for categories in (duplicate_category, duplicate_group, duplicate_membership_id, duplicate_user_id):
        with pytest.raises(ValueError):
            mirror_store.write_groups("1", categories, root=tmp_path)


@pytest.mark.parametrize(
    ("case", "roster_document"),
    [
        ("missing", None),
        # read_roster returns None for a corrupt or invalid on-disk document.
        ("corrupt", None),
        ("stale", {"state": "stale", "students": {}, "sections": {}}),
    ],
)
def test_roster_get_falls_back_live_when_mirror_is_not_current(
    monkeypatch, isolated_roster, case, roster_document,
):
    users = [{
        "id": 101,
        "name": "Live Ada",
        "sortable_name": "Ada, Live",
        "short_name": "Ada",
        "enrollments": [{"course_section_id": 44}],
    }]
    calls = []

    monkeypatch.setattr(roster_routes.mirror_store, "read_roster",
                        lambda course_id: roster_document)
    monkeypatch.setattr(roster_routes, "_fetch_students",
                        lambda course_id: (calls.append("students") or (users, None)))
    monkeypatch.setattr(roster_routes, "_fetch_sections",
                        lambda course_id: (calls.append("sections") or {"44": "Live section"}))
    monkeypatch.setattr(roster_routes, "load_group_categories", lambda course_id: ([], None, ""))

    data = client.get("/api/roster?course_id=1").json()

    assert data["ok"] is True, case
    assert data["students"][0]["display_name"] == "Live Ada"
    assert calls == ["students", "sections"]


def test_roster_get_handles_student_without_canvas_group(monkeypatch, isolated_roster):
    isolated_roster["group_schemes"] = {
        "1": {"selected_group_category_id": "7", "group_labels": {}}
    }
    users = [{
        "id": 101,
        "name": "Ada Lovelace",
        "sortable_name": "Lovelace, Ada",
        "short_name": "Ada",
        "enrollments": [{"course_section_id": 44}],
    }]
    groups = [{
        "category_id": "7",
        "category_name": "Reading tiers",
        "groups": [{"id": "8", "name": "Blue", "student_ids": []}],
    }]
    monkeypatch.setattr(roster_routes, "_fetch_students", lambda course_id: (users, None))
    monkeypatch.setattr(roster_routes, "_fetch_sections", lambda course_id: {"44": "Period 1"})
    monkeypatch.setattr(roster_routes, "load_group_categories", lambda course_id: (groups, None, ""))

    resp = client.get("/api/roster?course_id=1")
    data = resp.json()

    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["students"][0]["canvas_group"] is None
    assert data["counts"]["group_unset"] == 1
    assert "group_unset" in data["students"][0]["warnings"]


def test_create_group_set_with_groups(monkeypatch, isolated_roster):
    calls = []
    invalidations = []

    def fake_canvas_send(method, path, payload):
        calls.append((method, path, payload))
        if path == "/api/v1/courses/1/group_categories":
            return {"id": 7, "name": payload["name"]}, None
        if path == "/api/v1/group_categories/7/groups":
            return {"id": len(calls), "name": payload["name"]}, None
        return None, "unexpected call"

    monkeypatch.setattr(roster_routes, "_canvas_send", fake_canvas_send)
    monkeypatch.setattr(roster_routes, "_invalidate_group_snapshot",
                        lambda course_id: invalidations.append(course_id))

    resp = client.post("/api/roster/group-set", data={
        "course_id": "1",
        "name": "Reading groups",
        "group_names": '["Blue", "Green"]',
    })
    data = resp.json()

    assert data["ok"] is True
    assert data["group_category"]["id"] == 7
    assert [g["name"] for g in data["created_groups"]] == ["Blue", "Green"]
    assert isolated_roster["group_schemes"]["1"]["selected_group_category_id"] == "7"
    assert calls == [
        ("POST", "/api/v1/courses/1/group_categories", {"name": "Reading groups"}),
        ("POST", "/api/v1/group_categories/7/groups", {"name": "Blue"}),
        ("POST", "/api/v1/group_categories/7/groups", {"name": "Green"}),
    ]
    assert invalidations == ["1"]


def test_create_groups_rejects_existing_name(monkeypatch):
    groups = [{
        "category_id": "7",
        "category_name": "Reading tiers",
        "groups": [{"id": "8", "name": "Blue", "student_ids": []}],
    }]
    monkeypatch.setattr(roster_routes, "load_group_categories", lambda course_id: (groups, None, ""))

    resp = client.post("/api/roster/groups", data={
        "course_id": "1",
        "category_id": "7",
        "group_names": '["Blue"]',
    })
    data = resp.json()

    assert data["ok"] is False
    assert "already exists" in data["error"]


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


def test_roster_student_rejects_obsolete_tier_id(isolated_roster):
    """V3: tier_id is obsolete and should be rejected with clear error."""
    resp = client.post("/api/roster/student", data={
        "course_id": "1", "user_id": "101", "patch": '{"tier_id": "support"}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "obsolete" in data.get("error", "").lower()
    assert "canvas_group" in data.get("error", "").lower()


def test_roster_student_rejects_obsolete_tier(isolated_roster):
    """V3: tier is obsolete and should be rejected with clear error."""
    resp = client.post("/api/roster/student", data={
        "course_id": "1", "user_id": "101", "patch": '{"tier": "Support"}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "obsolete" in data.get("error", "").lower()


def test_roster_student_accepts_canvas_group(monkeypatch, isolated_roster):
    """V3: canvas_group writes the selected Canvas group membership."""
    calls = []
    monkeypatch.setattr(roster_routes, "load_group_categories",
                        lambda course_id: ([{
                            "category_id": "7",
                            "category_name": "Differentiation",
                            "groups": [{"id": "8", "name": "Blue", "student_ids": [], "memberships": []}],
                        }], None, ""))
    monkeypatch.setattr(roster_routes, "_update_student_canvas_group",
                        lambda *args: calls.append(args) or (True, None))
    resp = client.post("/api/roster/student", data={
        "course_id": "1", "user_id": "101",
        "patch": '{"canvas_group": {"category_id": "7", "group_id": "8"}}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert calls
    assert calls[0][:4] == ("1", "101", "7", "8")


def test_roster_group_membership_write_invalidates_only_after_success(monkeypatch, isolated_roster):
    invalidations = []
    monkeypatch.setattr(roster_routes, "load_group_categories", lambda course_id: ([{
        "category_id": "7", "category_name": "Differentiation",
        "groups": [{"id": "8", "name": "Blue", "student_ids": [], "memberships": []}],
    }], None, ""))
    monkeypatch.setattr(roster_routes, "_invalidate_group_snapshot",
                        lambda course_id: invalidations.append(course_id))
    monkeypatch.setattr(roster_routes, "_update_student_canvas_group",
                        lambda *args: (False, "Canvas denied"))

    failed = client.post("/api/roster/student", data={
        "course_id": "1", "user_id": "101",
        "patch": '{"canvas_group": {"category_id": "7", "group_id": "8"}}',
    }).json()

    assert failed["ok"] is False
    assert invalidations == []

    monkeypatch.setattr(roster_routes, "_update_student_canvas_group", lambda *args: (True, None))
    succeeded = client.post("/api/roster/student", data={
        "course_id": "1", "user_id": "101",
        "patch": '{"canvas_group": {"category_id": "7", "group_id": "8"}}',
    }).json()

    assert succeeded["ok"] is True
    assert invalidations == ["1"]


def test_roster_student_rejects_canvas_group_outside_category(monkeypatch, isolated_roster):
    monkeypatch.setattr(roster_routes, "load_group_categories",
                        lambda course_id: ([{
                            "category_id": "7",
                            "category_name": "Differentiation",
                            "groups": [{"id": "8", "name": "Blue", "student_ids": [], "memberships": []}],
                        }], None, ""))
    monkeypatch.setattr(roster_routes, "_update_student_canvas_group",
                        lambda *args: pytest.fail("_update_student_canvas_group should not be called"))
    resp = client.post("/api/roster/student", data={
        "course_id": "1", "user_id": "101",
        "patch": '{"canvas_group": {"category_id": "7", "group_id": "999"}}'
    })
    data = resp.json()
    assert data.get("ok") is False
    assert "invalid group_id" in data.get("error", "").lower()


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
    """V3: planned_group is obsolete and should be rejected with clear error."""
    resp = client.post("/api/roster/student", data={
        "course_id": "1", "user_id": "101",
        "patch": '{"planned_group": {"category_id": "7", "group_id": "8"}}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "obsolete" in data.get("error", "").lower()


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


def test_roster_bulk_rejects_obsolete_set_tier(isolated_roster):
    """V3: set_tier is obsolete."""
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": '["101"]',
        "action": "set_tier", "value": '{"tier_id": "support"}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "obsolete" in data.get("error", "").lower()


def test_roster_bulk_set_canvas_group(monkeypatch, isolated_roster):
    """V3: set_canvas_group writes Canvas membership for every selected user."""
    calls = []
    invalidations = []
    monkeypatch.setattr(roster_routes, "load_group_categories",
                        lambda course_id: ([{
                            "category_id": "7",
                            "category_name": "Differentiation",
                            "groups": [{"id": "8", "name": "Blue", "student_ids": [], "memberships": []}],
                        }], None, ""))
    monkeypatch.setattr(roster_routes, "_update_student_canvas_group",
                        lambda *args: calls.append(args) or (True, None))
    monkeypatch.setattr(roster_routes, "_invalidate_group_snapshot",
                        lambda course_id: invalidations.append(course_id))
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": '["101", "102"]',
        "action": "set_canvas_group", "value": '{"category_id": "7", "group_id": "8"}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("updated") == 2
    assert [c[:4] for c in calls] == [
        ("1", "101", "7", "8"),
        ("1", "102", "7", "8"),
    ]
    assert invalidations == ["1"]


def test_roster_bulk_rejects_canvas_group_outside_category(monkeypatch, isolated_roster):
    monkeypatch.setattr(roster_routes, "load_group_categories",
                        lambda course_id: ([{
                            "category_id": "7",
                            "category_name": "Differentiation",
                            "groups": [{"id": "8", "name": "Blue", "student_ids": [], "memberships": []}],
                        }], None, ""))
    monkeypatch.setattr(roster_routes, "_update_student_canvas_group",
                        lambda *args: pytest.fail("_update_student_canvas_group should not be called"))
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": '["101"]',
        "action": "set_canvas_group", "value": '{"category_id": "7", "group_id": "999"}'
    })
    data = resp.json()
    assert data.get("ok") is False
    assert "invalid group_id" in data.get("error", "").lower()


def test_roster_bulk_clear_canvas_group(monkeypatch, isolated_roster):
    """V3: clear_canvas_group should be accepted."""
    calls = []
    # Mock load_group_categories to return a valid category
    monkeypatch.setattr(roster_routes, "load_group_categories",
                        lambda course_id: ([{"category_id": "7", "category_name": "Test", "groups": []}], None, ""))
    monkeypatch.setattr(roster_routes, "_update_student_canvas_group",
                        lambda *args: calls.append(args) or (True, None))
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": '["101"]',
        "action": "clear_canvas_group", "value": '{"category_id": "7"}'
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("updated") == 1
    assert calls[0][:4] == ("1", "101", "7", None)


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


def test_roster_bulk_clear_tier_is_obsolete(isolated_roster):
    """V3: clear_tier is obsolete and should be rejected."""
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": '["101"]',
        "action": "clear_tier", "value": "{}"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "obsolete" in data.get("error", "").lower()


def test_roster_bulk_clear_planned_group_is_obsolete(isolated_roster):
    """V3: clear_planned_group is obsolete and should be rejected."""
    resp = client.post("/api/roster/bulk", data={
        "course_id": "1", "user_ids": '["101"]',
        "action": "clear_planned_group", "value": "{}"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert "obsolete" in data.get("error", "").lower()


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
