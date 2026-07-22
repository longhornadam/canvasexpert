r"""Long-path (Windows MAX_PATH) hardening — deep writers must not raise.

A long OneDrive root plus long course/assignment/student names can push a full
file path past Windows' legacy 260-char ceiling. Every workspace-relative writer
routes its I/O through ``workspace.extended_path`` so the write reaches the file
via the ``\\?\`` extended-length form. These tests exercise the shared write
primitives at paths that genuinely exceed 260 characters.
"""
import json
import os
from pathlib import Path

import pytest

from api import report_local_reads, storage_support
from api.webui import workspace

pytestmark = pytest.mark.skipif(os.name != "nt", reason="MAX_PATH 260-char limit is Windows-only")


def _deep_dir(tmp_path) -> str:
    """A directory nested deep enough that files inside exceed 260 chars."""
    deep = os.path.join(str(tmp_path), "D" * 80, "E" * 80, "F" * 80)
    assert len(deep) > 240
    return deep


def test_atomic_write_json_survives_deep_path(tmp_path):
    target = os.path.join(_deep_dir(tmp_path), "document.v1.json")
    assert len(target) > 260  # the length that used to raise FileNotFoundError

    # atomic_write_bytes creates the (deep) parent itself.
    storage_support.atomic_write_json(Path(target), {"schema": 1, "value": "first"})
    with open(workspace.extended_path(target), encoding="utf-8") as handle:
        assert json.load(handle)["value"] == "first"

    # Overwrite an existing deep target (the mirror rewrites constantly).
    storage_support.atomic_write_json(Path(target), {"schema": 1, "value": "second"})
    with open(workspace.extended_path(target), encoding="utf-8") as handle:
        assert json.load(handle)["value"] == "second"


def test_write_source_manifest_survives_deep_path(tmp_path):
    deep = _deep_dir(tmp_path)
    os.makedirs(workspace.extended_path(deep), exist_ok=True)

    report_local_reads.write_source_manifest(deep, {"essay.docx": {"tokens": 12}})
    manifest_path = os.path.join(deep, "_source_manifest.json")
    assert len(manifest_path) > 260
    with open(workspace.extended_path(manifest_path), encoding="utf-8") as handle:
        assert json.load(handle) == {"essay.docx": {"tokens": 12}}

    # A second write merges into the existing deep manifest (read + rewrite).
    report_local_reads.write_source_manifest(deep, {"notes.txt": {"tokens": 3}})
    with open(workspace.extended_path(manifest_path), encoding="utf-8") as handle:
        merged = json.load(handle)
    assert merged == {"essay.docx": {"tokens": 12}, "notes.txt": {"tokens": 3}}
