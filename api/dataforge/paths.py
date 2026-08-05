"""DataForge paths inside CanvasExpert's canonical workspace zones."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from api.platform_services import workspace


@dataclass(frozen=True)
class Paths:
    """Resolved DataForge paths.

    The workspace root is resolved at call time so tests and the host can
    switch workspace roots without stale module-level state. ``data_dir`` is
    retained as the private DataForge input root for the view-layer contract;
    each artifact is placed in its owning CanvasExpert zone.
    """

    data_dir: Path
    input_dir: Path
    output_dir: Path
    upload_dir: Path
    history_dir: Path
    anon_map: Path

    def ensure(self) -> "Paths":
        """Create the private and transient directories needed by DataForge."""
        for directory in (
            self.data_dir,
            self.input_dir,
            self.output_dir,
            self.upload_dir,
            self.history_dir,
            self.anon_map.parent,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return self


def _workspace_paths() -> Paths:
    root = workspace.workspace_root()
    if not root:
        raise RuntimeError("CanvasExpert workspace is not configured")

    student_work = Path(workspace.student_work_root(root))
    reports = Path(workspace.student_work_reports_root(root))
    system = Path(workspace.system_root(root))
    data_dir = student_work / "DataForge"
    system_data = system / "DataForge"
    transient = Path(tempfile.gettempdir()) / "CanvasExpert" / "DataForge"

    return Paths(
        data_dir=data_dir,
        input_dir=data_dir / "input",
        output_dir=reports / "DataForge",
        upload_dir=transient / "uploads",
        history_dir=system_data / "history",
        anon_map=system_data / "anonymize_map.csv",
    )


def get_paths(ensure: bool = True) -> Paths:
    paths = _workspace_paths()
    return paths.ensure() if ensure else paths
