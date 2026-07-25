"""Session-wide safety net: no test may touch this machine's real
config.json, profiles.json, or OneDrive-synced workspace.

A test that forgets to isolate these paths itself used to fall through to
the real machine state -- see the self-update brief's disclosed incident,
where an unmocked test wrote a fictional course into the real, live
OneDrive-synced settings.json. This fixture runs before every test in the
suite and points every known real-data path at a fresh, unique temp
location. A test's own explicit monkeypatch.setattr calls (e.g. migration
tests that deliberately exercise CONFIG_PATH/LEGACY_CONFIG_PATH) still take
effect normally, since they run after this fixture within the same test.
"""
import pytest

from api.webui import profiles, workspace
from api.webui.config import _io as config_io


@pytest.fixture(autouse=True)
def _isolate_real_machine_and_workspace_paths(tmp_path, monkeypatch):
    fake_root = tmp_path / "_isolated_runtime"

    monkeypatch.setattr(config_io, "CONFIG_PATH", str(fake_root / "config.json"))
    monkeypatch.setattr(config_io, "LEGACY_CONFIG_PATH", str(fake_root / "no-legacy-config.json"))
    monkeypatch.setattr(workspace, "CONFIG_PATH", str(fake_root / "config.json"))
    monkeypatch.setattr(workspace, "LEGACY_CONFIG_PATH", str(fake_root / "no-legacy-config.json"))
    monkeypatch.setattr(profiles, "PROFILES_PATH", str(fake_root / "profiles.json"))
    monkeypatch.setattr(profiles, "LEGACY_PROFILES_PATH", str(fake_root / "no-legacy-profiles.json"))

    # LOCALAPPDATA must be an explicit fake path, not unset: runtime_paths.local_app_dir()
    # falls back to Path.home() -- the real user profile -- when it's absent.
    monkeypatch.setenv("LOCALAPPDATA", str(fake_root / "LocalAppData"))
    # OneDrive/OneDriveCommercial are safe to simply unset: workspace.onedrive_root()
    # already treats "unset" as "no workspace", matching how most tests here already
    # model a no-workspace machine.
    monkeypatch.delenv("OneDrive", raising=False)
    monkeypatch.delenv("OneDriveCommercial", raising=False)
