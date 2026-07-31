"""Load the handwritten fixtures.

The fixtures are the spec in executable form, so this loader stays dumb: it
turns JSON into records and does no inference. Anything clever here would let a
fixture pass because the loader compensated for it.

Every name in every fixture is invented. Nothing under `fixtures/` came from a
real student, a real campus, or a real district.
"""
from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from api.dailywriting.core.models import AssignmentContext, ScaffoldBlock
from api.dailywriting.store.identity import MappingResolver

FIXTURE_ROOT = Path(__file__).resolve().parent


def _load(*parts: str) -> dict:
    return json.loads((FIXTURE_ROOT.joinpath(*parts)).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def roster(section: str = "section_2a") -> dict:
    return _load("rosters", f"{section}.json")


def vault_entries(section: str = "section_2a") -> list[dict]:
    """Roster rows in `api.feedback_vault` entry shape."""
    return list(roster(section)["entries"])


def roster_map(section: str = "section_2a", protected: set[str] | None = None):
    """Compiled roster scrub rules for a fixture section."""
    from api import feedback_scrub
    return feedback_scrub.build_replacement_map(vault_entries(section),
                                                protected or set())


def resolver(section: str = "section_2a") -> MappingResolver:
    return MappingResolver({entry["canvas_id"]: entry["pseudonym"]
                            for entry in vault_entries(section)})


def pseudonym_for(canvas_id: str, section: str = "section_2a") -> str:
    return resolver(section).to_pseudonym(canvas_id)


def real_names(section: str = "section_2a") -> set[str]:
    """Every real-name token and nickname on the fixture roster."""
    names: set[str] = set()
    for entry in vault_entries(section):
        names.add(entry["real_name"])
        names.update(entry["real_name"].split())
        names.update(entry.get("nicknames", []))
    return names


@lru_cache(maxsize=None)
def _reps() -> dict[str, dict]:
    return {rep["rep_id"]: rep for rep in _load("reps", "reps.json")["reps"]}


def rep(rep_id: str) -> AssignmentContext:
    raw = _reps()[rep_id]
    return AssignmentContext(
        rep_id=raw["rep_id"],
        date=datetime.fromisoformat(raw["date"]).date(),
        prompt_text=raw["prompt_text"],
        scaffold_blocks=[
            ScaffoldBlock(block_id=b["block_id"], template=b["template"],
                          kind=b["kind"])
            for b in raw.get("scaffold_blocks", [])
        ],
        source_texts=list(raw.get("source_texts", [])),
        word_cap=raw.get("word_cap"),
        section_id=raw.get("section_id"),
    )


def rep_ids() -> list[str]:
    return sorted(_reps())


@lru_cache(maxsize=None)
def _singles() -> dict[int, dict]:
    return {entry["fixture"]: entry
            for entry in _load("submissions", "singles.json")["submissions"]}


def single(fixture_number: int) -> dict:
    """One fixture's raw record: text plus the identifiers it arrived with."""
    return dict(_singles()[fixture_number])


def single_numbers() -> list[int]:
    return sorted(_singles())


@lru_cache(maxsize=None)
def _sequences() -> dict[int, dict]:
    return {entry["fixture"]: entry
            for entry in _load("submissions", "sequences.json")["sequences"]}


def sequence(fixture_number: int) -> dict:
    return dict(_sequences()[fixture_number])


def sequence_numbers() -> list[int]:
    return sorted(_sequences())


def submitted_at(raw: dict) -> datetime | None:
    value = raw.get("submitted_at")
    return datetime.fromisoformat(value) if value else None
