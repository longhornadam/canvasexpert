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
    return workspace.folder(SOURCE_FOLDER_NAME)


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
    if not folder or not os.path.isdir(folder):
        return []
    out: list[dict] = []
    root = Path(folder).resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTS | UNSUPPORTED_LEGACY_EXTS:
            continue
        rel = str(path.relative_to(root))
        out.append({
            "name": path.name,
            "relpath": rel,
            "path": str(path),
            "size": path.stat().st_size,
            "supported": path.suffix.lower() in SUPPORTED_EXTS,
        })
    return out


def _resolve_folder_file(relpath: str) -> Path:
    folder = ensure_source_folder()
    if not folder:
        raise ValueError("No Source Materials folder is available.")
    root = Path(folder).resolve()
    candidate = (root / relpath).resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError("Source-material path is outside the workspace folder.")
    if not candidate.is_file():
        raise ValueError(f"Source-material file not found: {relpath}")
    return candidate


def extract_folder_file(relpath: str) -> tuple[str, list[str]]:
    path = _resolve_folder_file(relpath)
    return extract_text_from_bytes(path.name, path.read_bytes())


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
