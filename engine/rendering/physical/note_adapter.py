"""Adapt NoteForge guided-cloze JSON into the print-document model."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from engine.rendering.physical.printdoc import BulletList, Heading, Para, PrintDoc, Slot

TAG_OPEN = "<NOTEFORGE_JSON>"
TAG_CLOSE = "</NOTEFORGE_JSON>"
_SLOT_RE = re.compile(r"\{\{(.+?)\}\}")


def load_noteforge_json(path: str | Path) -> dict[str, Any]:
    """Load a NoteForge JSON file, accepting optional NOTEFORGE_JSON tags."""

    text = Path(path).read_text(encoding="utf-8")
    return parse_noteforge_json(text)


def parse_noteforge_json(text: str) -> dict[str, Any]:
    """Parse a tagged or raw NoteForge JSON payload."""

    payload = _extract_noteforge_payload(text)
    return json.loads(payload)


def to_printdoc(note: dict[str, Any]) -> PrintDoc:
    """Convert guided-cloze NoteForge JSON to PrintDoc.

    Trusts the input shape; validation belongs upstream once NoteForge is wired
    into the live product.
    """

    blocks = []
    for block_index, block in enumerate(note.get("body", []) or []):
        block_type = block.get("type")
        if block_type == "heading":
            blocks.append(Heading(text=block.get("text", "") or ""))
        elif block_type == "paragraph":
            blocks.append(Para(runs=_parse_runs(block.get("text", "") or "", block_index)))
        elif block_type == "bullets":
            blocks.append(
                BulletList(
                    items=[
                        _parse_runs(item or "", f"{block_index}-{item_index}")
                        for item_index, item in enumerate(block.get("items", []) or [])
                    ]
                )
            )

    return PrintDoc(
        title=note.get("title", "Untitled Notes") or "Untitled Notes",
        instructions=note.get("topic", "") or "",
        blocks=blocks,
        answer_key=None,
    )


def _parse_runs(text: str, prefix) -> list:
    parts = _SLOT_RE.split(text)
    runs = []
    slot_index = 0

    for index, segment in enumerate(parts):
        if index % 2 == 0:
            if segment:
                runs.append(segment)
        else:
            runs.append(
                Slot(
                    id=f"b{prefix}s{slot_index}",
                    content_html=segment.strip(),
                    key=True,
                )
            )
            slot_index += 1

    return runs


def _extract_noteforge_payload(text: str) -> str:
    start = text.find(TAG_OPEN)
    if start == -1:
        trimmed = text.strip()
        if trimmed.startswith("{"):
            return trimmed
        raise ValueError("NOTEFORGE_JSON tags not found.")

    end = text.find(TAG_CLOSE, start + len(TAG_OPEN))
    if end == -1 or end <= start:
        end = len(text)

    payload = text[start + len(TAG_OPEN) : end].strip()
    if not payload:
        raise ValueError("Tagged JSON payload is empty.")
    return payload
