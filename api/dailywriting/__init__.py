"""Daily writing practice substrate.

Students write one short piece per class day ("a rep"). An automated checker
scores it against a published checklist, the student sees feedback the next
morning, and the teacher reads the aggregate weekly.

This package is the substrate only: data model, segmentation, history-blind
scoring, evidence-backed observations, directive/uptake tracking, rolling
profile regeneration, and a teacher weekly digest. It performs no Canvas
writes, creates no gradebook columns, and promotes no student to a new tier.

Load-bearing invariants (each has a test in api/tests/dailywriting/):

  INV-1  Scoring is history-blind. `core.scoring.score_submission` cannot
         reach a profile, a pseudonym, or a record store.
  INV-2  History drives feedback and sequencing only.
  INV-3  Every observation carries a dated, quoted, scrubbed span.
  INV-4  The rolling profile is regenerated from a bounded window, never
         appended to, and never reads a prior profile.
  INV-5  Profiles carry writing fields only, enforced by a key whitelist.
  INV-6  Anything in a profile is renderable to the student.
  INV-7  Names never leave the tenant. Text is scrubbed at ingest, before
         any span is stored, because names appear inside student writing.
"""
from __future__ import annotations

__all__ = ["config", "core", "store"]
