"""Shared helpers for the daily writing tests.

The session-wide isolation fixture in `api/tests/conftest.py` applies here too,
which is why these tests live under `api/tests/`: it keeps them off the real
config, the real profiles, and the real OneDrive-synced workspace.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from api.dailywriting.config import criteria_loader
from api.dailywriting.core import directives as directives_module
from api.dailywriting.core import ingest as ingest_module
from api.dailywriting.core.models import Directive
from api.dailywriting.fixtures import loader


@pytest.fixture(scope="session")
def criteria() -> dict:
    return criteria_loader.load_all_tiers()


@pytest.fixture
def roster_map():
    return loader.roster_map()


@pytest.fixture
def ingest_fixture(criteria, roster_map):
    """Run one numbered single fixture through the whole ingest path."""

    def _run(fixture_number: int, *, protected: set[str] | None = None):
        raw = loader.single(fixture_number)
        context = loader.rep(raw["rep_id"])
        return ingest_module.ingest(
            submission_id=raw["submission_id"],
            rep_id=raw["rep_id"],
            pseudonym_id=loader.pseudonym_for(raw["canvas_id"]),
            submitted_at=loader.submitted_at(raw),
            text=raw["text"],
            context=context,
            criteria_set=criteria[context.tier],
            roster_map=roster_map,
            protected=protected if protected is not None else set(),
        )

    return _run


@pytest.fixture
def run_sequence(criteria, roster_map):
    """Run one numbered sequence fixture rep by rep through the real path.

    Returns (directive, acknowledgments, compiled). The directive is threaded
    through ingest rather than evaluated separately, so the test exercises the
    ordering the production path uses.
    """

    def _run(fixture_number: int):
        spec = loader.sequence(fixture_number)
        raw_directive = spec["directive"]
        compiled = directives_module.compile_directive(raw_directive["prose"])
        pseudonym = loader.pseudonym_for(spec["canvas_id"])
        directive = Directive(
            directive_id=raw_directive["directive_id"],
            pseudonym_id=pseudonym,
            issued_at=datetime.fromisoformat(raw_directive["issued_at"]),
            text=raw_directive["prose"],
            target_pattern=raw_directive["target_pattern"],
            detector=compiled.detector,
        )

        live = [directive]
        acknowledgments = []
        for entry in spec["reps"]:
            context = loader.rep(entry["rep_id"])
            if entry.get("missing"):
                live = ingest_module.record_gap(live, entry["rep_id"])
                continue
            result = ingest_module.ingest(
                submission_id=entry["submission_id"],
                rep_id=entry["rep_id"],
                pseudonym_id=pseudonym,
                submitted_at=loader.submitted_at(entry),
                text=entry["text"],
                context=context,
                criteria_set=criteria[context.tier],
                open_directives=live,
                roster_map=roster_map,
                protected=set(),
                now=loader.submitted_at(entry),
            )
            live = result.directives
            acknowledgments.extend(result.acknowledgments)

        return live[0], acknowledgments, compiled

    return _run
