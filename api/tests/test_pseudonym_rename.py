"""Carrying a pseudonym rename through every store that keeps one on disk.

The ordering is the whole point and it is not symmetric: assessment history has
to be prepared BEFORE the vault forgets the old pseudonym, and stored writing
has to be rewritten AFTER the new one exists. These tests pin that order, and
pin that a teacher who has never used either feature can still rename a
student.

The manual-rename and regenerate routes exercised here are the live
`POST /api/roster/student` Roster Console route -- the dead
`/api/names/pseudonym` and `/api/names/pseudonym/regenerate` routes were
deleted rather than ported, but the rename-ordering law lives in the shared
`roster_updates.update_student` updater both the Web UI and MCP call, so the
law is exercised the same way either route reaches it.
"""
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api import feedback_vault, pseudonym_rename
from api.feedback_vault import Vault
from api.webui import server
from api.webui.routes import names as names_routes
from api.webui.routes import roster as roster_routes
from api.webui.routes import roster_updates

_WORDS = feedback_vault._REGISTRY_WORDS


def _vault(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    vault.get_or_assign("9001", "Synthetic One", "SIS-1")
    vault.set_pseudonym("9001", _WORDS[0])
    vault.save()
    return vault


def test_current_pseudonym_does_not_mint_for_an_unknown_student(tmp_path):
    """Asking what the old name was must not create one as a side effect, which
    `get_or_assign` would."""
    vault = _vault(tmp_path)
    before = len(vault)
    assert pseudonym_rename.current_pseudonym(vault, "9001") == _WORDS[0]
    assert pseudonym_rename.current_pseudonym(vault, "does-not-exist") == ""
    assert pseudonym_rename.current_pseudonym(vault, "") == ""
    assert len(vault) == before


def test_a_no_op_rename_rewrites_nothing(monkeypatch):
    """Same name in and out, or a missing name, must not walk the writing store."""
    def explode(*args, **kwargs):  # pragma: no cover - must never be reached
        raise AssertionError("the writing store must not be opened for a no-op")

    monkeypatch.setattr(
        "api.dailywriting.store.repo.Repository.default", explode)
    assert pseudonym_rename.rewrite_writing_spans("Same Name", "Same Name") == ""
    assert pseudonym_rename.rewrite_writing_spans("", "New Name") == ""
    assert pseudonym_rename.rewrite_writing_spans("Old Name", "") == ""


def test_an_unconfigured_feature_never_blocks_a_rename(monkeypatch):
    """A teacher who has never opened Assessments, or never ingested writing,
    must still be able to rename a student."""
    monkeypatch.setattr(
        "api.dataforge.paths.get_paths",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("workspace not configured")))
    assert pseudonym_rename.backfill_assessment_history() == ""

    monkeypatch.setattr(
        "api.dailywriting.store.repo.Repository.default",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no writing store")))
    assert pseudonym_rename.rewrite_writing_spans("Alpha Oneton", "Beta Twoton") == ""


def test_a_rename_never_brings_a_workspace_folder_into_being(tmp_path, monkeypatch):
    """Regression: `get_paths()` defaults to ensure=True, which creates the
    DataForge folders. Calling it from a rename created them on a machine that
    has never opened Assessments, and when a workspace root resolves to a
    relative path it created them under the current directory instead.
    `api/tests/test_work_registry.py` guards the same property for the
    workbench registry."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("api.platform_services.workspace.workspace_root", lambda: "")

    assert pseudonym_rename.backfill_assessment_history() == ""
    assert pseudonym_rename.refresh_published_profile() == ""

    assert not (tmp_path / "_System").exists()
    assert not list(tmp_path.iterdir()), "a rename must not write anything here"


def test_a_failed_rewrite_is_reported_and_names_both_pseudonyms(monkeypatch, tmp_path):
    """Until the rewrite succeeds the retired pseudonym is still sitting in
    stored text, so this cannot report success. The message has to carry both
    names because the vault no longer knows the old one."""
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setattr(
        "api.dailywriting.store.repo.workspace_store_root", lambda: store)
    monkeypatch.setattr(
        "api.dailywriting.store.repo.Repository.default", lambda *a, **k: object())
    monkeypatch.setattr(
        "api.dailywriting.cli.rewrite_pseudonym.rewrite_pseudonym",
        lambda *a, **k: (_ for _ in ()).throw(OSError("disk went away")))

    message = pseudonym_rename.rewrite_writing_spans("Alpha Oneton", "Beta Twoton")
    assert "Alpha Oneton" in message
    assert "Beta Twoton" in message
    assert "Retry" in message


def _published(monkeypatch, tmp_path):
    """A stale published profile in a synthetic For AI zone, with the rest of the
    DataForge workspace stubbed so a rebuild is reachable.

    Both the For AI zone and the history folder derive from one workspace root
    in production, so stubbing only the first would model a state that cannot
    happen: a published profile with no workspace behind it.
    """
    from api.dataforge import profile_export

    monkeypatch.setattr(
        "api.pseudonym_rename.workspace.for_ai_root", lambda: str(tmp_path / "For AI"))
    monkeypatch.setattr(
        "api.dataforge.paths.get_paths",
        lambda *a, **k: SimpleNamespace(history_dir=tmp_path / "history"))
    monkeypatch.setattr(
        "api.dataforge.identity.VaultIdentity.from_paths",
        classmethod(lambda cls, paths: object()))
    target = tmp_path / "For AI" / "DataForge" / profile_export.PROFILE_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"students": {"Alpha Oneton": {}}}', encoding="utf-8")
    return target


def test_nothing_published_means_nothing_to_refresh(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "api.pseudonym_rename.workspace.for_ai_root", lambda: str(tmp_path / "For AI"))

    def explode(*args, **kwargs):  # pragma: no cover - must never be reached
        raise AssertionError("must not rebuild a profile that was never published")

    monkeypatch.setattr("api.dataforge.profile_export.publish_profile", explode)
    assert pseudonym_rename.refresh_published_profile() == ""


def test_a_published_profile_is_rebuilt_so_it_stops_serving_the_old_name(monkeypatch, tmp_path):
    target = _published(monkeypatch, tmp_path)
    rebuilt = []
    monkeypatch.setattr(
        "api.dataforge.profile_export.publish_profile",
        lambda paths, anonymizer=None, **k: rebuilt.append(anonymizer) or target)

    assert pseudonym_rename.refresh_published_profile() == ""
    assert len(rebuilt) == 1, "the stale artifact must be regenerated"
    assert rebuilt[0] is not None, "the rebuild resolves current pseudonyms via the vault"
    assert target.exists()


def test_a_profile_that_cannot_be_rebuilt_is_removed_rather_than_left_stale(monkeypatch, tmp_path):
    """An absent profile makes get_standards_profile say it needs generating,
    which is honest. Serving a retired pseudonym is not."""
    target = _published(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "api.dataforge.profile_export.publish_profile",
        lambda *a, **k: (_ for _ in ()).throw(OSError("history unreadable")))

    assert pseudonym_rename.refresh_published_profile() == ""
    assert not target.exists(), "a profile that cannot be rebuilt must not survive"


def _wire_order(monkeypatch, tmp_path, *, rewrite_error=""):
    """Record the order of the two side effects around the vault write."""
    calls = []
    vault = _vault(tmp_path)
    # roster.py captured its own `_vault` reference at import time (`from
    # .names import _vault`), so the live rename route's factory must be
    # patched on roster_routes itself -- patching names_routes._vault would
    # not reach it.
    monkeypatch.setattr(roster_routes, "_vault", lambda: vault)

    def backfill():
        calls.append(("backfill", pseudonym_rename.current_pseudonym(vault, "9001")))
        return ""

    def rewrite(old, new):
        calls.append(("rewrite", old, new))
        return rewrite_error

    # roster_updates.py imports the same `api.pseudonym_rename` module object
    # names.py does, so patching it here reaches both entry points.
    monkeypatch.setattr(roster_updates.pseudonym_rename, "backfill_assessment_history", backfill)
    monkeypatch.setattr(roster_updates.pseudonym_rename, "rewrite_writing_spans", rewrite)
    return calls, vault


def _rename_via_roster(pseudonym=None, *, regenerate=False):
    patch = {"regenerate_pseudonym": True} if regenerate else {"pseudonym": pseudonym}
    return TestClient(server.app).post(
        "/api/roster/student",
        data={"course_id": "1", "user_id": "9001", "patch": json.dumps(patch)})


def test_the_manual_rename_route_prepares_history_then_rewrites_writing(monkeypatch, tmp_path):
    calls, vault = _wire_order(monkeypatch, tmp_path)
    response = _rename_via_roster(_WORDS[1])

    assert response.status_code == 200
    assert response.json()["ok"] is True
    # The backfill ran while the vault still held the old name, and the rewrite
    # ran afterward with both names in hand.
    assert calls == [
        ("backfill", _WORDS[0]),
        ("rewrite", _WORDS[0], _WORDS[1]),
    ]
    assert pseudonym_rename.current_pseudonym(vault, "9001") == _WORDS[1]


def test_the_regenerate_route_carries_the_rename_through_too(monkeypatch, tmp_path):
    calls, vault = _wire_order(monkeypatch, tmp_path)
    response = _rename_via_roster(regenerate=True)

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert [call[0] for call in calls] == ["backfill", "rewrite"]
    assert calls[0][1] == _WORDS[0]
    minted = calls[1][2]
    assert calls[1][1] == _WORDS[0]
    assert pseudonym_rename.current_pseudonym(vault, "9001") == minted


def test_an_unfinished_rewrite_surfaces_instead_of_reporting_success(monkeypatch, tmp_path):
    """The name is saved by then, so this cannot be silent: the teacher has to
    know the writing record still refers to the old one."""
    _wire_order(monkeypatch, tmp_path, rewrite_error=f"stored writing still says {_WORDS[0]}")
    response = _rename_via_roster(_WORDS[1])

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert _WORDS[0] in response.json()["error"]


def test_a_refused_collision_never_reaches_the_writing_store(monkeypatch, tmp_path):
    """A rename that the vault rejects must not rewrite anything, or stored text
    would move to a name no student holds."""
    calls, vault = _wire_order(monkeypatch, tmp_path)
    vault.get_or_assign("9002", "Synthetic Two", "SIS-2")
    vault.set_pseudonym("9002", _WORDS[2])
    vault.save()

    response = _rename_via_roster(_WORDS[2])

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert [call[0] for call in calls] == ["backfill"], "the rewrite must not have run"
    assert pseudonym_rename.current_pseudonym(vault, "9001") == _WORDS[0]
