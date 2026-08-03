"""Repository safety laws for DataForge assessment artifacts."""

from pathlib import Path
import subprocess


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_assessment_workbooks_and_reidentification_maps_are_ignored():
    for relative_path in (
        "api/dataforge/assessment.xlsx",
        "api/dataforge/anonymize_map.csv",
    ):
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "-q", relative_path],
            cwd=REPOSITORY_ROOT,
            check=False,
        )
        assert result.returncode == 0, f"{relative_path} is not protected by .gitignore"
