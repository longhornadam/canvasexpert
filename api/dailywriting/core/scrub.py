"""Name removal for student writing (INV-7).

Names appear inside student writing: a kid names a classmate in a paragraph
about the assigned reading. So every submission is scrubbed against the roster
vault, which is the authoritative list of the people this product is
responsible for. `api.feedback_scrub` maps every real name, nickname and id in
the vault to that student's stable pseudonym, case-insensitively and
word-bounded, longest match first. The teacher supplies the names and the
nicknames; a name that needs covering and is not there yet is added directly,
in the names screen, where a teacher can see and correct it.

This module used to run a second, heuristic pass on top: any capitalised token
with no entry in a hand-maintained lexicon was assumed to be a name and
replaced. It was removed deliberately, and should not come back.

The reasoning, measured on realistic seventh-grade responses with no roster
name anywhere in them, so every removal was wrong: 30 of 37 capitalised
tokens redacted. `Gettysburg`, `Photosynthesis`, `Canada`, `Equator`, `Dogs`.
A history paragraph stored as "The [name] of [name] was the turning point of
the [name] [name]." The assignment's own text was exempt, which only helped
when the prompt happened to name the same proper nouns; a student writing past
the prompt, which is the writing most worth coaching, was hit hardest. And
because scrubbing happens before storage, that was the stored record, the
quoted structural evidence derived from the writing.

Over-redaction was defended as the safe direction. It is not safe, it is
destructive: this product exists to help a teacher read how a student's
writing is developing, and it cannot do that from text with holes punched
through it. The residual risk the removal accepts is a non-roster first name
-- a cousin, a kid at another school -- reaching the teacher's own AI tenant
inside a quoted sentence. That is the trade this product makes, and it is the
same one `api/feedback_pipeline.py` already makes on the PowerGrader path,
which has never done heuristic detection and sends student writing to a model
every week.

Scrubbing happens at ingest, before segmentation, and the unscrubbed text is
never persisted. That ordering is the whole defence: a scrub bolted on later
has already been outrun by the spans quoted out of the text.

Pure stdlib apart from two optional Canvas Expert lookups, both lazily
imported so this module stays offline-testable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from api.dailywriting.core.models import ScrubFinding

# Used only by `model_ready_text`, to strip the vault's safe pseudonyms out of
# a payload leaving the tenant. Readable in a teacher's record, unlike an
# opaque token.
NAME_PLACEHOLDER = "[name]"


class ScrubLeakError(RuntimeError):
    """A real roster name survived scrubbing. Never store the text."""


class UnsanitizedOutboundError(ValueError):
    """An external-model boundary was given text that never passed scrub."""


@dataclass(frozen=True)
class ScrubResult:
    text: str
    findings: list[ScrubFinding]


@dataclass(frozen=True)
class ModelReadyText:
    """A scrubbed string approved for a future external-model call.

    No client is built in this substrate.  This small typed boundary is the
    only representation that a later client may accept, so raw strings are
    rejected before they can become an outbound payload.
    """

    text: str


def build_roster_map(vault) -> list[tuple]:
    """Compiled roster replacement rules for `vault`, longest match first."""
    from api import feedback_scrub
    # The second argument is `protected`, which `build_replacement_map`
    # accepts and ignores; `api/mcp_server/pseudonym.py` passes an empty set
    # for the same reason. Roster identity is the only thing scrubbed here, so
    # there is nothing to shield from it.
    return feedback_scrub.build_replacement_map(vault.entries(), set())


def _locate_findings(text: str, needle: str, kind: str) -> list[ScrubFinding]:
    """Findings for every occurrence of `needle` in the final text.

    `detail` stays empty on purpose: a finding is written to the same private
    store as everything else, and recording the value that was removed would
    reintroduce exactly what the removal took out.
    """
    findings: list[ScrubFinding] = []
    if not needle:
        return findings
    start = text.find(needle)
    while start != -1:
        findings.append(ScrubFinding(
            kind=kind,  # type: ignore[arg-type]
            replacement=needle,
            span_start=start,
            span_end=start + len(needle),
        ))
        start = text.find(needle, start + len(needle))
    return findings


def _roster_pass(text: str, roster_map: list[tuple]) -> tuple[str, list[ScrubFinding]]:
    """Apply the vault's rules, then locate what landed."""
    from api import feedback_scrub

    if not roster_map:
        return text, []
    scrubbed = feedback_scrub.scrub_text(text, roster_map)
    if scrubbed == text:
        return scrubbed, []

    findings: list[ScrubFinding] = []
    findings.extend(_locate_findings(
        scrubbed, feedback_scrub.ID_PLACEHOLDER, "roster_id"))
    # One finding per pseudonym token now present that was not there before,
    # which is the closest honest account of "a roster name was here".
    for replacement in sorted({r for _p, r in roster_map
                               if r and r != feedback_scrub.ID_PLACEHOLDER}):
        added = scrubbed.count(replacement) - text.count(replacement)
        if added <= 0:
            continue
        for finding in _locate_findings(scrubbed, replacement, "roster_name")[:added]:
            findings.append(finding)
    return scrubbed, findings


def scrub_writing(
    text: str,
    *,
    vault=None,
    roster_map: list[tuple] | None = None,
) -> ScrubResult:
    """Scrub student writing for storage. Call this at ingest, before anything
    reads or quotes the text.

    Supply either `vault` or a prebuilt `roster_map`. Pass neither and nothing
    is removed, which is right for a fixture with no roster and never right in
    production -- `assert_clean_for_storage` is the backstop that catches a
    caller who forgot, and it raises rather than storing the text.

    Everything the roster knows goes: real name, first, last, every nickname
    the teacher entered, and Canvas/SIS ids. Nothing else is guessed at. A name
    that keeps appearing and is not covered belongs in the vault, added in the
    names screen, not inferred here from capitalisation.
    """
    if text is None:
        return ScrubResult(text="", findings=[])

    rules = roster_map
    if rules is None and vault is not None:
        rules = build_roster_map(vault)

    scrubbed, findings = _roster_pass(text, rules or [])
    return ScrubResult(text=scrubbed, findings=findings)


def assert_clean_for_storage(text: str, vault=None) -> None:
    """Raise if any real roster name survived. Call before persisting a span.

    Cheap, and it is the difference between a bug and a disclosure.
    """
    if vault is None or not text:
        return
    from api import feedback_scrub
    survivors = feedback_scrub.verify_clean(text, vault)
    if survivors:
        raise ScrubLeakError(
            f"{len(survivors)} real name(s) survived scrubbing; refusing to "
            "store this text. Check the vault's nickname coverage for this "
            "section."
        )


def model_ready_text(
    scrubbed: ScrubResult,
    *,
    pseudonyms: Iterable[str],
    vault=None,
) -> ModelReadyText:
    """Create the only future-model input representation from scrub output.

    A raw ``str`` is refused even if it happens not to contain a name: callers
    must establish the scrub-before-any-downstream-work ordering explicitly.
    Tenant-side records may retain the vault's safe pseudonyms, but an
    external-model payload may not, so the caller must supply its section's
    pseudonyms and this boundary removes them. The roster survivor check
    remains useful when a vault is available.
    """
    if not isinstance(scrubbed, ScrubResult):
        raise UnsanitizedOutboundError(
            "outbound text must be a ScrubResult from scrub_writing(), not a "
            "raw string"
        )
    known_pseudonyms = {p.strip() for p in pseudonyms if p and p.strip()}
    if not known_pseudonyms:
        raise UnsanitizedOutboundError(
            "outbound text requires the section pseudonyms so none can leave "
            "the tenant"
        )
    text = scrubbed.text
    for pseudonym in sorted(known_pseudonyms, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(pseudonym)}\b", NAME_PLACEHOLDER,
                      text, flags=re.IGNORECASE)
    assert_clean_for_storage(text, vault)
    return ModelReadyText(text=text)
