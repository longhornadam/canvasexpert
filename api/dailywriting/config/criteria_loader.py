"""Load published criteria sets from `config/criteria/*.json`."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from api.dailywriting.core.models import CriteriaSet, CriterionItem

CRITERIA_DIR = Path(__file__).resolve().parent / "criteria"

TIER_FILES = {
    1: "tier1_thesis.json",
    2: "tier2_argument.json",
    3: "tier3_evidence.json",
    4: "tier4_commentary.json",
}


class CriteriaFileError(ValueError):
    """A criteria file is missing a required field or is malformed."""


def parse_criteria_set(document: dict) -> CriteriaSet:
    required = ("criteria_set_id", "tier", "version", "published_at", "items")
    missing = [key for key in required if key not in document]
    if missing:
        raise CriteriaFileError(f"criteria file missing field(s) {missing}")

    items: list[CriterionItem] = []
    for raw in document["items"]:
        item_missing = [key for key in
                        ("item_id", "label", "student_facing_text",
                         "check_description", "check_id") if key not in raw]
        if item_missing:
            raise CriteriaFileError(
                f"criterion {raw.get('item_id', '?')} missing {item_missing}")
        items.append(CriterionItem(
            item_id=raw["item_id"],
            label=raw["label"],
            student_facing_text=raw["student_facing_text"],
            check_description=raw["check_description"],
            check_id=raw["check_id"],
        ))

    return CriteriaSet(
        criteria_set_id=document["criteria_set_id"],
        tier=int(document["tier"]),
        version=int(document["version"]),
        items=items,
        published_at=datetime.fromisoformat(document["published_at"]),
        spot_emphasis=document.get("spot_emphasis"),
    )


def load_criteria_file(path: Path | str) -> CriteriaSet:
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CriteriaFileError(f"no criteria file at {path}") from exc
    except json.JSONDecodeError as exc:
        raise CriteriaFileError(f"{path.name} is not valid JSON: {exc}") from exc
    return parse_criteria_set(document)


def load_tier(tier: int, *, criteria_dir: Path | None = None) -> CriteriaSet:
    """Load the published checklist for a tier.

    Tiers are additive and item ids are stable across them on purpose: a
    student who advances from tier 2 to tier 3 keeps their met-rate history on
    `arguable`, because it is the same criterion, still being measured.
    """
    if tier not in TIER_FILES:
        raise CriteriaFileError(f"no criteria published for tier {tier}")
    base = criteria_dir or CRITERIA_DIR
    return load_criteria_file(base / TIER_FILES[tier])


def load_all_tiers(*, criteria_dir: Path | None = None) -> dict[int, CriteriaSet]:
    return {tier: load_tier(tier, criteria_dir=criteria_dir)
            for tier in sorted(TIER_FILES)}
