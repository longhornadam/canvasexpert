"""Source-material helpers for PowerGrader AI scoring.

Teachers usually keep passages as PDFs, Word docs, slide decks, or pasted text.
This module is the public facade: workspace paths, source-material listing,
context assembly, token estimation, warnings, and response presets.

File-format decoding and normalization live in
``api.webui.source_material_extractors``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import workspace
from .source_material_extractors import (
    MAX_EXTRACTED_CHARS,
    SUPPORTED_EXTS,
    UNSUPPORTED_LEGACY_EXTS,
    _collapse_ws,
    _truncate,
    extract_text_from_bytes,
)


SOURCE_FOLDER_NAME = "Source Materials"

RESPONSE_PRESETS = {
    "scr": {
        "label": "SCR - single paragraph",
        "response_words": 130,
        "output_tokens_per_student": 350,
    },
    "ecr": {
        "label": "ECR - 4-5 paragraphs",
        "response_words": 650,
        "output_tokens_per_student": 600,
    },
}


def source_folder() -> str | None:
    return workspace.library_folder(SOURCE_FOLDER_NAME)


def ensure_source_folder() -> str | None:
    folder = source_folder()
    if folder:
        os.makedirs(folder, exist_ok=True)
    return folder


def _estimate_tokens_for_text(text: str) -> int:
    return max(0, len(text or "") // 4)


def estimate_text_tokens(text: str) -> int:
    return _estimate_tokens_for_text(text)


def list_source_files() -> list[dict]:
    folder = ensure_source_folder()
    if not folder or not os.path.isdir(workspace.extended_path(folder)):
        return []
    out: list[dict] = []
    # os.walk over an extended root: teacher subfolders can nest past Windows'
    # 260-char limit, where Path.rglob silently skips files. Relative paths are
    # computed against the extended root (the \\?\ prefix cancels out), then the
    # public "path" is rebuilt plain so callers/UI stay prefix-free.
    plain_root = os.path.abspath(folder)
    ext_root = workspace.extended_path(plain_root)
    for dirpath, _dirnames, filenames in os.walk(ext_root):
        for name in filenames:
            suffix = os.path.splitext(name)[1].lower()
            if suffix not in SUPPORTED_EXTS | UNSUPPORTED_LEGACY_EXTS:
                continue
            ext_full = os.path.join(dirpath, name)
            rel = os.path.relpath(ext_full, ext_root)
            out.append({
                "name": name,
                "relpath": rel,
                "path": os.path.join(plain_root, rel),
                "size": os.path.getsize(ext_full),
                "supported": suffix in SUPPORTED_EXTS,
            })
    out.sort(key=lambda item: item["relpath"])
    return out


def _resolve_folder_file(relpath: str) -> str:
    folder = ensure_source_folder()
    if not folder:
        raise ValueError("No Source Materials folder is available.")
    # Use the extended-path-safe canonical helper: os.path.realpath follows
    # symlinks/junctions but can fail past MAX_PATH.  We resolve the root and
    # candidate through a long-path-safe canonical helper, compare resolved
    # targets with Windows case-insensitive containment, and return the
    # resolved in-tree target.
    root_ext = workspace.extended_path(os.path.abspath(folder))
    candidate = os.path.abspath(os.path.join(folder, relpath))
    # Resolve through extended path for symlink/junction following past MAX_PATH
    try:
        resolved_root = os.path.realpath(workspace.extended_path(folder))
        resolved_candidate = os.path.realpath(workspace.extended_path(candidate))
    except OSError:
        # realpath I/O can fail past MAX_PATH; fall back to lexical containment
        resolved_root = os.path.abspath(folder)
        resolved_candidate = os.path.abspath(candidate)
    # Case-insensitive containment check for Windows
    root_norm = os.path.normcase(resolved_root)
    candidate_norm = os.path.normcase(resolved_candidate)
    if os.path.commonpath([root_norm, candidate_norm]) != root_norm:
        raise ValueError("Source-material path is outside the workspace folder.")
    # Use the extended path for the actual read-back check
    ext_candidate = workspace.extended_path(candidate)
    if not os.path.isfile(ext_candidate):
        raise ValueError(f"Source-material file not found: {relpath}")
    return candidate


def extract_folder_file(relpath: str) -> tuple[str, list[str]]:
    path = _resolve_folder_file(relpath)
    with open(workspace.extended_path(path), "rb") as handle:
        data = handle.read()
    return extract_text_from_bytes(os.path.basename(path), data)


def parse_source_files_json(value: str) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(x) for x in parsed if str(x).strip()]


def build_source_context(
    *,
    pasted_text: str = "",
    folder_files: list[str] | None = None,
    uploaded_files: list | None = None,
    strict: bool = False,
) -> dict:
    materials: list[dict] = []
    warnings: list[str] = []
    errors: list[str] = []

    pasted = (pasted_text or "").strip()
    if pasted:
        text, truncated = _truncate(_collapse_ws(pasted))
        if truncated:
            warnings.append(
                f"Pasted source material was truncated to {MAX_EXTRACTED_CHARS:,} characters."
            )
        materials.append({
            "title": "Pasted source material",
            "source": "pasted",
            "text": text,
            "chars": len(text),
            "tokens_est": estimate_text_tokens(text),
        })

    for relpath in folder_files or []:
        try:
            text, file_warnings = extract_folder_file(relpath)
            warnings.extend(file_warnings)
            materials.append({
                "title": Path(relpath).name,
                "source": f"Source Materials/{relpath}",
                "text": text,
                "chars": len(text),
                "tokens_est": estimate_text_tokens(text),
            })
        except Exception as e:
            errors.append(f"{relpath}: {e}")

    for upload in uploaded_files or []:
        filename = getattr(upload, "filename", "") or "uploaded file"
        if not filename:
            continue
        try:
            fileobj = getattr(upload, "file", None)
            if fileobj is None:
                continue
            data = fileobj.read()
            text, file_warnings = extract_text_from_bytes(filename, data)
            warnings.extend(file_warnings)
            materials.append({
                "title": Path(filename).name,
                "source": "uploaded file",
                "text": text,
                "chars": len(text),
                "tokens_est": estimate_text_tokens(text),
            })
        except Exception as e:
            errors.append(f"{filename}: {e}")

    if strict and errors:
        raise ValueError("; ".join(errors))

    total_text = "\n\n".join(m["text"] for m in materials)
    total_tokens = estimate_text_tokens(total_text)
    return {
        "materials": materials,
        "warnings": warnings,
        "errors": errors,
        "tokens_est": total_tokens,
        "chars": len(total_text),
    }


def context_warnings(context: dict) -> list[str]:
    warnings = list((context or {}).get("warnings") or [])
    tokens = int((context or {}).get("tokens_est") or 0)
    if tokens >= 100_000:
        warnings.append(
            "This looks book-sized. Whole books can get expensive quickly, especially "
            "if you retry or compare multiple models. Use excerpts when possible."
        )
    elif tokens >= 50_000:
        warnings.append(
            "This is a very large source context. Use an excerpt unless the whole text "
            "is truly needed for scoring."
        )
    elif tokens >= 10_000:
        warnings.append(
            "This is a long source context. Cost is still estimated as fresh input; "
            "provider caching is not guaranteed."
        )
    return warnings


def response_preset(kind: str) -> dict:
    return RESPONSE_PRESETS.get((kind or "scr").lower(), RESPONSE_PRESETS["scr"])


def synthetic_student_response(kind: str) -> str:
    preset = response_preset(kind)
    return ("student response " * int(preset["response_words"])).strip()
