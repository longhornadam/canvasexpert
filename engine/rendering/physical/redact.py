"""Deterministic tier redaction for PrintDoc Slot content."""

from __future__ import annotations

import copy
import hashlib
import math
from collections.abc import Iterator
from dataclasses import fields, is_dataclass
from typing import Any

from engine.rendering.physical.printdoc import PrintDoc, Slot
from engine.rendering.physical.tiers import TIER_BLANK_FRACTION


def redact(printdoc: PrintDoc, tier: str) -> PrintDoc:
    """Return a redacted copy of ``printdoc`` for the requested tier."""

    if tier not in TIER_BLANK_FRACTION:
        raise ValueError(f"unknown tier: {tier!r}")

    doc = copy.deepcopy(printdoc)
    key_slots = [slot for slot in _iter_slots(doc) if slot.key]
    key_slots.sort(key=lambda slot: hashlib.sha256(slot.id.encode("utf-8")).digest())

    n_blank = math.ceil(TIER_BLANK_FRACTION[tier] * len(key_slots))
    for index, slot in enumerate(key_slots):
        slot.given = index >= n_blank

    return doc


def filled(printdoc: PrintDoc) -> PrintDoc:
    """Return a copy with every slot shown as filled content."""

    doc = copy.deepcopy(printdoc)
    for slot in _iter_slots(doc):
        slot.given = True
    return doc


def iter_slots(doc: Any) -> Iterator[Slot]:
    """Yield every Slot found in ``doc``."""

    yield from _iter_slots(doc)


def _iter_slots(value: Any) -> Iterator[Slot]:
    if isinstance(value, Slot):
        yield value
        return

    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_slots(item)
        return

    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from _iter_slots(item)
        return

    if is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            yield from _iter_slots(getattr(value, field.name))
