"""Retained Writing Record test helpers."""
from __future__ import annotations

import pytest

from api.dailywriting.core import ingest
from api.dailywriting.fixtures import loader


@pytest.fixture
def roster_map():
    return loader.roster_map()


@pytest.fixture
def ingest_fixture(roster_map):
    def _ingest(number: int):
        raw = loader.single(number)
        context = loader.rep(raw["rep_id"])
        return ingest.ingest(
            submission_id=raw["submission_id"],
            rep_id=raw["rep_id"],
            pseudonym_id=loader.pseudonym_for(raw["canvas_id"]),
            submitted_at=loader.submitted_at(raw),
            text=raw["text"],
            context=context,
            roster_map=roster_map,
        )
    return _ingest
