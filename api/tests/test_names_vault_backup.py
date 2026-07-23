import json
import os
import re

from api.webui import workspace
from api.webui.routes import names


def test_backup_vault_filename_matches_run_stamp_format(tmp_path, monkeypatch):
    """The vault backup filename used to be vault-YYYY-MM-DD_HH-MM-SS.json --
    a different separator style from every other run-stamped teacher-visible
    name. It now matches workspace.RUN_STAMP_FORMAT."""
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    vault_dir = workspace.identity_vault_dir()
    os.makedirs(vault_dir, exist_ok=True)
    with open(os.path.join(vault_dir, "vault.json"), "w", encoding="utf-8") as f:
        f.write("{}")

    response = names.backup_vault()
    body = json.loads(response.body)

    assert body["ok"] is True
    backup_name = os.path.basename(body["path"])
    assert re.fullmatch(r"vault-\d{8}-\d{6}-\d{6}\.json", backup_name)
