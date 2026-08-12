import json
import os

from api.platform_services import workspace
from api.webui.routes import names


def _mount(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    vault_dir = workspace.identity_vault_dir()
    os.makedirs(vault_dir, exist_ok=True)
    return vault_dir


def test_no_conflict_returns_empty_file_list(tmp_path, monkeypatch):
    vault_dir = _mount(tmp_path, monkeypatch)
    with open(os.path.join(vault_dir, "vault.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"schema_version": 3, "by_canvas_id": {}}))

    response = names.vault_conflict()
    body = json.loads(response.body)

    assert body == {"ok": True, "folder": vault_dir, "files": []}


def test_conflict_files_report_name_size_and_mtime_not_contents(tmp_path, monkeypatch):
    vault_dir = _mount(tmp_path, monkeypatch)
    with open(os.path.join(vault_dir, "vault.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"schema_version": 3, "by_canvas_id": {}}))
    conflict_path = os.path.join(vault_dir, "vault-OTHERPC.json")
    with open(conflict_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"by_canvas_id": {"999": {"real_name": "Someone Real", "pseudonym": "Fake Person"}}}))

    response = names.vault_conflict()
    body = json.loads(response.body)

    assert body["ok"] is True
    assert body["folder"] == vault_dir
    assert len(body["files"]) == 1
    entry = body["files"][0]
    assert entry["name"] == "vault-OTHERPC.json"
    assert entry["size_bytes"] == os.path.getsize(conflict_path)
    assert entry["modified_at"]
    dumped = json.dumps(body)
    assert "Someone Real" not in dumped
    assert "Fake Person" not in dumped
