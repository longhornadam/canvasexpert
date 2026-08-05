import json

from api.feedback_vault import Vault
from api.mcp_server import tools
from api.platform_services import workspace


def _profile_workspace(monkeypatch, tmp_path, profile):
    root = tmp_path / "workspace"
    target = root / "For AI" / "DataForge" / "standards-profile.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(profile), encoding="utf-8")
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(root))
    vault_path = tmp_path / "vault.json"
    monkeypatch.setattr(tools, "_vault_factory", lambda: Vault(str(vault_path)))
    return root


def _profile():
    return {
        "format": "dataforge.standards_profile.v1",
        "generated": "2026-08-03",
        "grain": "learning_standard",
        "weak_below": 70.0,
        "snapshots_used": 1,
        "snapshots_without_standard_list": 0,
        "student_count": 1,
        "note": "Pseudonyms only.",
        "students": {
            "Sparky McGee": {
                "assessments": 1,
                "latest_pct": 68.0,
                "latest_date": "2026-08-01",
                "standards": {},
                "weak_standards": [],
            }
        },
    }


def test_get_standards_profile_returns_valid_published_artifact(monkeypatch, tmp_path):
    _profile_workspace(monkeypatch, tmp_path, _profile())

    result = tools.get_standards_profile()

    assert result == {"ok": True, "profile": _profile()}


def test_get_standards_profile_missing_artifact_is_structured(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(root))
    monkeypatch.setattr(tools, "_vault_factory", lambda: Vault(str(tmp_path / "vault.json")))

    result = tools.get_standards_profile()

    assert result == {
        "ok": False,
        "error": "DataForge standards profile unavailable: generate it locally first.",
    }


def test_get_standards_profile_rejects_malformed_and_wrong_format(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    target = root / "For AI" / "DataForge" / "standards-profile.json"
    target.parent.mkdir(parents=True)
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(root))
    monkeypatch.setattr(tools, "_vault_factory", lambda: Vault(str(tmp_path / "vault.json")))

    target.write_text("{not json", encoding="utf-8")
    assert tools.get_standards_profile() == {
        "ok": False,
        "error": "DataForge standards profile unavailable: the published artifact is malformed.",
    }

    target.write_text(json.dumps({"format": "other.v1"}), encoding="utf-8")
    assert tools.get_standards_profile() == {
        "ok": False,
        "error": "DataForge standards profile unavailable: unsupported artifact format.",
    }


def test_get_standards_profile_withholds_safety_violation_without_echoing_private_value(
    monkeypatch, tmp_path
):
    profile = _profile()
    profile["canvas_id"] = "990001"
    _profile_workspace(monkeypatch, tmp_path, profile)

    class SyntheticVault:
        def all_real_identifiers(self):
            return {"Alice Adams"}, {"990001"}

    monkeypatch.setattr(tools, "_vault_factory", SyntheticVault)
    result = tools.get_standards_profile()

    assert result == {
        "ok": False,
        "error": "DataForge standards profile withheld: the outbound safety gate is not green.",
    }
    assert "990001" not in json.dumps(result)


def test_get_standards_profile_server_wrapper_is_compact(monkeypatch):
    from api.mcp_server import server

    monkeypatch.setattr(tools, "get_standards_profile", lambda: {"ok": True, "profile": {}})
    wire = server.get_standards_profile()

    assert wire == '{"ok":true,"profile":{}}'


def test_get_assessment_context_server_wrapper_is_compact(monkeypatch):
    from api.mcp_server import server

    monkeypatch.setattr(
        tools, "get_assessment_context",
        lambda course_id, pseudonyms="": {
            "ok": True, "course_id": course_id, "pseudonyms": pseudonyms,
        },
    )
    wire = server.get_assessment_context("synthetic-course", " Alpha, alpha ")

    assert wire == (
        '{"ok":true,"course_id":"synthetic-course",'
        '"pseudonyms":" Alpha, alpha "}'
    )


def test_product_guide_names_dataforge_review_and_privacy_boundary():
    guide = tools.get_product_guide()["guide"]

    for phrase in (
        "Assessments",
        "get_standards_profile",
        "Identity Vault",
        "pseudonymized, not anonymous",
        "reviewed group",
    ):
        assert phrase in guide
