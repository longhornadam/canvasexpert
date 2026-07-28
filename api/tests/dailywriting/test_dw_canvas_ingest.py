"""Canvas-sourced ingest: catalog + mirror -> AssignmentContext -> the store.

Fabricated data uses generic names ("Learner One") and made-up Canvas ids,
never a real district (same convention as `test_mcp_server_tools.py`). The
vault and workspace are isolated to `tmp_path` per test.
"""
from __future__ import annotations

import ast
import os
import sys
from datetime import date

# Same bootstrap as test_mcp_server_tools.py: api/mcp_server/pseudonym.py
# reaches sibling top-level api/ modules with bare names, which only resolves
# once api/ itself is on sys.path.
_API_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_REPO_ROOT = os.path.dirname(_API_DIR)
for _path in (_API_DIR, _REPO_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import pytest

from api import course_catalog, feedback_safety
from api.dailywriting import canvas_ingest, canvas_source
from api.dailywriting.cli import _common
from api.dailywriting.cli import ingest_canvas as cli_ingest_canvas
from api.dailywriting.cli import score as cli_score
from api.dailywriting.core import ingest as core_ingest_module
from api.dailywriting.core import scrub
from api.dailywriting.fixtures import loader
from api.dailywriting.store.identity import MappingResolver, VaultResolver
from api.dailywriting.store.repo import Repository
from api.feedback_vault import Vault
from api.mcp_server import tools
from api.mirror import store as mirror_store
from api.powergrader import context as pg_context
from api.webui import workspace

COURSE_ID = "111"
ASSIGNMENT_ID = "700010"
_ANY_YEAR = (date(2026, 1, 1), date(2026, 12, 31))

FIXTURE_USERS = [
    {"id": 900001, "name": "Learner One", "sortable_name": "One, Learner",
     "short_name": "Lee", "sis_user_id": "SIS-900001",
     "enrollments": [{"course_section_id": 800001}]},
    {"id": 900002, "name": "Learner Two", "sortable_name": "Two, Learner",
     "short_name": "Learner Two", "sis_user_id": "SIS-900002",
     "enrollments": [{"course_section_id": 800001}]},
]
SECTION_MAP = {"800001": "Period 1"}


def _mount(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))


def _write_catalog(root, *, description="Write one paragraph.", due_at="2026-09-14T23:59:00Z",
                   assignment_id=ASSIGNMENT_ID, submission_types=("online_text_entry",)):
    row = {
        "id": assignment_id, "name": "Essay 1", "description": description,
        "points_possible": 10, "due_at": due_at, "unlock_at": None, "lock_at": None,
        "created_at": "2026-09-01T00:00:00Z", "updated_at": "2026-09-01T00:00:00Z",
        "published": True, "submission_types": list(submission_types),
        "assignment_group_id": 44,
    }
    assignment = course_catalog.normalize_assignment(row)
    now = mirror_store.now_iso()
    scope = lambda records: {"state": "current", "last_success_at": now,
                             "last_attempt_at": now, "error_code": "", "records": records}
    document = {
        "version": course_catalog.CATALOG_VERSION,
        "course_id": COURSE_ID,
        "course_name": "Course 111",
        "updated_at": now,
        "assignments": scope({assignment_id: assignment}),
        "modules": scope([]),
        "assignment_groups": scope([]),
    }
    course_catalog.write_catalog(document, root=root)
    return assignment


def _write_mirror(root, *, bodies_by_user, assignment_id=ASSIGNMENT_ID, extra_subs=()):
    mirror_store.write_roster(COURSE_ID, FIXTURE_USERS, SECTION_MAP, root=root)
    mirror_store.write_assignments(COURSE_ID, [
        {"id": assignment_id, "name": "Essay 1", "due_at": "2026-09-14T23:59:00Z",
         "points_possible": 10},
    ], root=root)
    rows = [
        {"assignment_id": assignment_id, "user_id": uid, "workflow_state": "submitted",
         "submitted_at": submitted_at, "body": body}
        for uid, (body, submitted_at) in bodies_by_user.items()
    ]
    mirror_store.merge_submissions(COURSE_ID, assignment_id, rows + list(extra_subs),
                                   root=root, replace=True)
    mirror_store.record_pass(COURSE_ID, "full", ok=True, root=root)


def _repository(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    repository = Repository(tmp_path / "store", resolver=VaultResolver(vault), vault=vault)
    return repository, vault


def _bind_tools(monkeypatch, repository, vault):
    """Make `get_writing_history` read the same store/vault the ingest wrote."""
    monkeypatch.setattr(tools, "_vault_factory", lambda: vault)
    monkeypatch.setattr(tools, "_dailywriting_repository_factory", lambda: repository)


def _history(pseudonym, **kwargs):
    """`get_writing_history`, with an explicit window wide enough to hold
    every fixture date here regardless of the real machine clock -- the
    tool's own default lookback is relative to `date.today()`, and these
    fixtures are dated 2026 on purpose (matching the rest of this package's
    fixtures), which can fall outside that default window."""
    return tools.get_writing_history(pseudonym, since="2020-01-01",
                                     until="2030-12-31", **kwargs)


# --- AC1/AC2/AC3: happy path, idempotent re-run, no leak ---------------------

def test_ingest_then_get_writing_history_has_no_score_and_ascending_order(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    root = str(tmp_path)
    _write_catalog(root)
    _write_mirror(root, bodies_by_user={
        # Later submitted_at listed first in the dict, to prove the payload
        # is actually sorted rather than accidentally already in order.
        900002: ("<p>Second student's paragraph about the topic.</p>", "2026-09-14T21:00:00Z"),
        900001: ("<p>First student's paragraph about the topic.</p>", "2026-09-14T20:00:00Z"),
    })
    repository, vault = _repository(tmp_path)
    _bind_tools(monkeypatch, repository, vault)

    log = list(canvas_ingest.ingest_canvas_assignment(COURSE_ID, ASSIGNMENT_ID,
                                                       repository=repository))
    assert any("2 submission(s) ingested" in line for line in log)

    resolver = VaultResolver(vault)
    pseudonym_one = resolver.to_pseudonym("900001")
    pseudonym_two = resolver.to_pseudonym("900002")

    for pseudonym in (pseudonym_one, pseudonym_two):
        history = _history(pseudonym)
        assert len(history["submissions"]) == 1
        row = history["submissions"][0]
        assert row["total"] is None
        assert row["possible"] is None
        assert row["status"] is None
        assert "per_item" not in row

    submitted_ats = sorted(
        s.submitted_at for pseudonym in (pseudonym_one, pseudonym_two)
        for s in repository.submissions_in_window(pseudonym, *_ANY_YEAR))
    assert [t.isoformat() for t in submitted_ats] == [
        "2026-09-14T20:00:00+00:00", "2026-09-14T21:00:00+00:00"]


def test_ingest_twice_is_read_idempotent(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    root = str(tmp_path)
    _write_catalog(root)
    _write_mirror(root, bodies_by_user={
        900001: ("<p>A paragraph, written once.</p>", "2026-09-14T20:00:00Z"),
    })
    repository, vault = _repository(tmp_path)
    _bind_tools(monkeypatch, repository, vault)

    list(canvas_ingest.ingest_canvas_assignment(COURSE_ID, ASSIGNMENT_ID, repository=repository))
    pseudonym = VaultResolver(vault).to_pseudonym("900001")
    first = _history(pseudonym)
    assert len(first["submissions"]) == 1

    list(canvas_ingest.ingest_canvas_assignment(COURSE_ID, ASSIGNMENT_ID, repository=repository))
    second = _history(pseudonym)
    assert len(second["submissions"]) == 1
    assert second["submissions"][0]["submission_id"] == first["submissions"][0]["submission_id"]
    assert second == first


def test_no_real_name_leaks_into_get_writing_history(monkeypatch, tmp_path):
    """AC3: a roster real name embedded in another student's submission text
    must scrub before it can be quoted back out through get_writing_history."""
    _mount(monkeypatch, tmp_path)
    root = str(tmp_path)
    _write_catalog(root)
    _write_mirror(root, bodies_by_user={
        900001: ("<p>My friend Learner Two helped me plan this paragraph.</p>",
                 "2026-09-14T20:00:00Z"),
        900002: ("<p>An unrelated paragraph about the topic.</p>", "2026-09-14T20:05:00Z"),
    })
    repository, vault = _repository(tmp_path)
    _bind_tools(monkeypatch, repository, vault)

    list(canvas_ingest.ingest_canvas_assignment(COURSE_ID, ASSIGNMENT_ID, repository=repository))

    pseudonym_one = VaultResolver(vault).to_pseudonym("900001")
    # The submitted body above carries a roster real name; confirm the scrub
    # removed it on the way in, so the scan below is checking scrubbed bytes
    # rather than text that never carried a name in the first place.
    stored = repository.submissions_in_window(pseudonym_one, *_ANY_YEAR)[0]
    assert "Learner Two" not in stored.raw_text

    result = _history(pseudonym_one, include_text=True)
    assert result["ok"] is True
    verdict = feedback_safety.scan_payload(result, vault)
    assert verdict["green"] is True
    assert verdict["soft"] == []


def test_scrub_bypass_would_be_caught_by_the_storage_leak_guard(monkeypatch, tmp_path):
    """Positive control for the test above: if `_process`'s scrub step were
    ever bypassed, the store's own `assert_clean_for_storage` guard (already
    wired into `Repository.append_submission`) raises rather than silently
    storing the leak -- so the green/soft assertion above is not vacuously
    true just because nothing in this fixture happens to trip it."""
    _mount(monkeypatch, tmp_path)
    root = str(tmp_path)
    _write_catalog(root)
    _write_mirror(root, bodies_by_user={
        900001: ("<p>My friend Learner Two helped me plan this paragraph.</p>",
                 "2026-09-14T20:00:00Z"),
    })
    repository, _vault = _repository(tmp_path)

    monkeypatch.setattr(
        core_ingest_module.scrub, "scrub_writing",
        lambda text, **_: scrub.ScrubResult(text=text, findings=[]))

    with pytest.raises(scrub.ScrubLeakError):
        list(canvas_ingest.ingest_canvas_assignment(COURSE_ID, ASSIGNMENT_ID,
                                                     repository=repository))


# --- AC4: structured refusal on a missing/stale catalog or mirror -----------

def test_missing_catalog_refuses_without_writing(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    root = str(tmp_path)
    _write_mirror(root, bodies_by_user={900001: ("<p>Text.</p>", "2026-09-14T20:00:00Z")})
    repository, _vault = _repository(tmp_path)

    with pytest.raises(canvas_ingest.CanvasIngestError, match="catalog"):
        list(canvas_ingest.ingest_canvas_assignment(COURSE_ID, ASSIGNMENT_ID,
                                                     repository=repository))
    assert repository.read_rep(canvas_source.rep_id_for(COURSE_ID, ASSIGNMENT_ID)) is None


def test_unknown_assignment_id_refuses(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    root = str(tmp_path)
    _write_catalog(root)
    _write_mirror(root, bodies_by_user={900001: ("<p>Text.</p>", "2026-09-14T20:00:00Z")})
    repository, _vault = _repository(tmp_path)

    with pytest.raises(canvas_ingest.CanvasIngestError, match="No assignment"):
        list(canvas_ingest.ingest_canvas_assignment(COURSE_ID, "999999", repository=repository))


def test_stale_mirror_refuses_without_writing(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    root = str(tmp_path)
    _write_catalog(root)
    # Roster/submissions written, but no sync pass has ever recorded success
    # -- the "missing" half of AC4's "stale or missing".
    mirror_store.write_roster(COURSE_ID, FIXTURE_USERS, SECTION_MAP, root=root)
    mirror_store.write_assignments(COURSE_ID, [
        {"id": ASSIGNMENT_ID, "name": "Essay 1", "due_at": "2026-09-14T23:59:00Z"},
    ], root=root)
    mirror_store.merge_submissions(COURSE_ID, ASSIGNMENT_ID, [
        {"assignment_id": ASSIGNMENT_ID, "user_id": 900001, "workflow_state": "submitted",
         "submitted_at": "2026-09-14T20:00:00Z", "body": "<p>Text.</p>"},
    ], root=root, replace=True)
    repository, _vault = _repository(tmp_path)

    with pytest.raises(canvas_ingest.CanvasIngestError, match="CanvasMirror"):
        list(canvas_ingest.ingest_canvas_assignment(COURSE_ID, ASSIGNMENT_ID,
                                                     repository=repository))
    assert repository.read_rep(canvas_source.rep_id_for(COURSE_ID, ASSIGNMENT_ID)) is None


# --- AC5: a submission author missing from the identity vault ---------------

def test_unknown_author_is_skipped_and_reported_not_fatal(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    root = str(tmp_path)
    _write_catalog(root)
    # 900001 is on the roster (gets a vault entry via roster sync); 900099 is
    # not -- a submission from someone the roster sync never covered.
    _write_mirror(root, bodies_by_user={
        900001: ("<p>A real paragraph from an enrolled student.</p>", "2026-09-14T20:00:00Z"),
    }, extra_subs=[
        {"assignment_id": ASSIGNMENT_ID, "user_id": 900099, "workflow_state": "submitted",
         "submitted_at": "2026-09-14T20:00:00Z", "body": "<p>From someone off the roster.</p>"},
    ])
    repository, vault = _repository(tmp_path)
    _bind_tools(monkeypatch, repository, vault)

    log = list(canvas_ingest.ingest_canvas_assignment(COURSE_ID, ASSIGNMENT_ID,
                                                       repository=repository))
    assert any("1 submission(s) ingested" in line for line in log)
    assert any("1 skipped (no identity-vault entry" in line for line in log)

    pseudonym = VaultResolver(vault).to_pseudonym("900001")
    result = _history(pseudonym)
    assert len(result["submissions"]) == 1
    with pytest.raises(Exception):
        VaultResolver(vault).to_pseudonym("900099")


# --- AC6: a Canvas-sourced rep refuses to be checklist-scored ---------------

def test_score_cli_refuses_a_canvas_sourced_rep(monkeypatch, tmp_path, capsys):
    _mount(monkeypatch, tmp_path)
    root = str(tmp_path)
    _write_catalog(root)
    _write_mirror(root, bodies_by_user={
        900001: ("<p>An extended piece, not a daily rep.</p>", "2026-09-14T20:00:00Z"),
    })
    repository, vault = _repository(tmp_path)
    list(canvas_ingest.ingest_canvas_assignment(COURSE_ID, ASSIGNMENT_ID, repository=repository))
    pseudonym = VaultResolver(vault).to_pseudonym("900001")

    # cli.score's non-identity-map path builds its Repository via
    # `Repository.default()`, which reads the vault through
    # `api.powergrader.context.vault()` -- bind that seam to our vault.
    monkeypatch.setattr(pg_context, "vault", lambda: vault)

    exit_code = cli_score.main([
        "--from", "2026-09-01", "--to", "2026-09-30",
        "--students", pseudonym,
        "--store-root", str(repository.root),
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "skipped" in out
    assert "not a real tier" in out
    submission_ids = [s.submission_id for s in
                      repository.submissions_in_window(pseudonym, *_ANY_YEAR)]
    assert repository.scores_for(submission_ids) == {}


def test_is_unscorable_true_for_canvas_sourced_context_false_for_a_real_tier():
    row = course_catalog.normalize_assignment({
        "id": "1", "name": "x", "description": "", "due_at": "2026-09-14T23:59:00Z",
    })
    unscored = canvas_source.assignment_context(row, rep_id="canvas:1:1")
    assert canvas_source.is_unscorable(unscored) is True

    scored = loader.rep(loader.rep_ids()[0])
    assert canvas_source.is_unscorable(scored) is False


# --- AC7: an assignment with an empty description still ingests ------------

def test_empty_description_ingests_with_visibly_empty_prompt(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    root = str(tmp_path)
    _write_catalog(root, description="")
    _write_mirror(root, bodies_by_user={
        900001: ("<p>A paragraph against a blank prompt.</p>", "2026-09-14T20:00:00Z"),
    })
    repository, vault = _repository(tmp_path)
    _bind_tools(monkeypatch, repository, vault)

    list(canvas_ingest.ingest_canvas_assignment(COURSE_ID, ASSIGNMENT_ID, repository=repository))

    rep = repository.read_rep(canvas_source.rep_id_for(COURSE_ID, ASSIGNMENT_ID))
    assert rep.prompt_text == ""

    pseudonym = VaultResolver(vault).to_pseudonym("900001")
    result = _history(pseudonym)
    assert result["submissions"][0]["prompt_text"] == ""


# --- date derivation (Section 5.1) ------------------------------------------

def test_rep_date_falls_back_due_then_unlock_then_created():
    assert canvas_source.rep_date({"due_at": "2026-09-14T23:59:00Z",
                                   "unlock_at": "2026-09-01T00:00:00Z",
                                   "created_at": "2026-08-01T00:00:00Z"}
                                  ).isoformat() == "2026-09-14"
    assert canvas_source.rep_date({"due_at": "", "unlock_at": "2026-09-01T00:00:00Z",
                                   "created_at": "2026-08-01T00:00:00Z"}
                                  ).isoformat() == "2026-09-01"
    assert canvas_source.rep_date({"due_at": "", "unlock_at": "",
                                   "created_at": "2026-08-01T00:00:00Z"}
                                  ).isoformat() == "2026-08-01"


def test_rep_date_refuses_rather_than_inventing_a_date():
    with pytest.raises(canvas_source.DateDerivationError):
        canvas_source.rep_date({"id": "1", "due_at": "", "unlock_at": "", "created_at": ""})


# --- AC8: no Canvas transport import ----------------------------------------

def test_no_new_module_imports_canvas_transport():
    forbidden_modules = {"requests", "api.canvas", "api.submission_transport",
                         "api.webui.canvas_client"}
    for module in (canvas_source, canvas_ingest, cli_ingest_canvas):
        tree = ast.parse(open(module.__file__, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {node.module} if node.module else set()
            else:
                continue
            hit = names & forbidden_modules
            assert not hit, f"{module.__name__} imports forbidden {hit}"


# --- CLI parity --------------------------------------------------------------

def test_cli_ingest_canvas_runs_the_same_driver(monkeypatch, tmp_path, capsys):
    _mount(monkeypatch, tmp_path)
    root = str(tmp_path)
    _write_catalog(root)
    _write_mirror(root, bodies_by_user={
        900001: ("<p>Text for the CLI parity path.</p>", "2026-09-14T20:00:00Z"),
    })
    identity_path = tmp_path / "identity.json"
    identity_path.write_text('{"900001": "Fixture Pseudonym"}', encoding="utf-8")

    exit_code = cli_ingest_canvas.main([
        "--course-id", COURSE_ID, "--assignment-id", ASSIGNMENT_ID,
        "--identity-map", str(identity_path),
        "--store-root", str(tmp_path / "store"),
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "1 submission(s) ingested" in out

    repository = Repository(tmp_path / "store",
                            resolver=MappingResolver({"900001": "Fixture Pseudonym"}),
                            vault=None)
    submissions = repository.submissions_in_window("Fixture Pseudonym", *_ANY_YEAR)
    assert len(submissions) == 1


def test_cli_ingest_canvas_surfaces_the_refusal_as_a_command_error(monkeypatch, tmp_path, capsys):
    _mount(monkeypatch, tmp_path)
    identity_path = tmp_path / "identity.json"
    identity_path.write_text("{}", encoding="utf-8")

    exit_code = _common.run(cli_ingest_canvas.main, [
        "--course-id", COURSE_ID, "--assignment-id", ASSIGNMENT_ID,
        "--identity-map", str(identity_path),
        "--store-root", str(tmp_path / "store"),
    ])
    assert exit_code == 2
    out = capsys.readouterr().out
    assert "error:" in out
    assert "catalog" in out
