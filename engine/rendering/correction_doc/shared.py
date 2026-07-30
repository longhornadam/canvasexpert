"""Shared helpers for correction document rendering."""

from __future__ import annotations

import html
import re
from typing import Dict, List, Tuple

from ...spec_engine.models import RationalesEntry


def _build_item_index(items: List[Dict]) -> Dict[str, Dict]:
    return {item["id"]: item for item in items if isinstance(item.get("id"), str)}


def _choice_letter(choice: Dict, index: int) -> str:
    cid = choice.get("id")
    if isinstance(cid, str) and cid:
        return cid.upper()
    return chr(65 + index)


def _build_rationale_index(rationales: List[RationalesEntry]) -> Dict[str, RationalesEntry]:
    return {r.item_id: r for r in rationales}


def _strip_html(text: str) -> str:
    text = re.sub(r"</(p|div|br|li|h[1-6])[^>]*>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _items_to_render(
    items: List[Dict],
    rationale_index: Dict[str, RationalesEntry],
) -> List[Tuple[int, Dict, RationalesEntry]]:
    result = []
    q_number = 1
    for item in items:
        qtype = item.get("type", "")
        if qtype in ("STIMULUS", "STIMULUS_END"):
            continue
        item_id = item.get("id")
        if item_id and item_id in rationale_index:
            result.append((q_number, item, rationale_index[item_id]))
        q_number += 1
    return result
