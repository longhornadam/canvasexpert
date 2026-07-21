# Seating - feature concept overview

Status: concept / planning only (2026-07-21). Not an execution brief. No code, no
acceptance criteria yet. This captures the shape of the idea so a later brief can carve
slices out of it.

## What it is

A local Seating surface in Canvas Expert: a teacher builds their classroom, seats
students, and prints charts. The angle that a standalone tool (the inspiration was
seatsaavy.com) cannot match is the Canvas tie-in. We already hold the roster mirror and
can hold several grouping dimensions per student, so seating can be aware of who works
well together, who needs space, and who has an accommodation, and it can round-trip
groupings back into Canvas.

## Trust model (the one invariant)

The security line is not "read only." It is: the AI never handles real identity.

```
AI  <->  CM/CE  <->  Canvas Live
```

- The AI proposes groupings and seatings against pseudonyms (Sparky McGee), and can
  request writes.
- CM/CE holds the identity vault, de-pseudonymizes, and is the only actor that touches
  Canvas: grades, comments, feedback, assignment pushes, and now group sets/groups.
- Creating a Canvas group set is just another CM/CE-mediated mutation on the same trusted
  path as a grade push, so "push these groups to Canvas" stays inside the posture.

Everything the Seating feature stores lives in the private workspace and never syncs to
the model. Free-text notes and reasons stay on the machine and are never included in any
MCP payload; only structured enums are.

## Canvas grouping fact this rests on

Within one Canvas group set a student has exactly one membership. But a student holds one
membership per set across many sets independently. So academic tier, interests, and any
other axis can each be their own group set with no conflict. That is what makes the
multi-dimensional grouping idea Canvas-native rather than a workaround.

## Data model

All local, keyed by vault id, so the AI only ever sees pseudonyms.

- `GroupingDimension` - a named axis (academic tier, interests, etc.) that mirrors a Canvas
  group set. Holds its buckets, a `source` (mirror-derived or teacher-authored), and a
  `canvasSync` state (`none` / `export-csv` / `live`) plus `canvasGroupSetId` once CM/CE
  creates it.
- `Membership` - one row per (student, dimension). Enforces one-per-set locally so a push
  can't conflict.
- `Relationship` - authored, local, never Canvas. `type` is `pair` / `separate` /
  `accommodation`; `strength` is `hard` or `soft`; carries an optional `region`
  (front, near-teacher) and a local free-text `note`.
- `Room` - physical, one per section. Holds the orientation anchors (front, teacher desk,
  door, windows). Fixed.
- `RoomState` - a named setup within a section (Testing, Pairs, 4-tops). Owns its furniture
  clusters, a soft-objective profile, and a pointer to its current assignment.
- `SeatingAssignment` - who sits where for a given setup, versioned with a timestamp.
- `AdjacencyLedger` - derived, not authored. Counts how often each pair has been neighbors
  across the retained chart history for the section.

## Neighbor graph (derived from geometry)

Adjacency is not stored, it falls out of the furniture kind:

- table / pod / duo / trio: small shared surface, everyone in the cluster is a mutual
  neighbor.
- rows: left/right in the same row is a neighbor; directly in front/behind is a weaker
  neighbor; diagonal is not.

This one rule set feeds the ledger, defines what `separate` forbids and what `pair` wants,
and makes pods inherently stickier than rows for the novelty objective. Switching a class
from rows to pods recomputes everything downstream with no re-authoring.

## Lenses

The same room can be viewed through any grouping dimension: seats color-code by academic
tier, or by distractibility, or by interests. Each lens is a separate Canvas group set
underneath (for the ones that sync). Distractibility-style axes stay local only by default
and are never pushed to Canvas, since a group set named for that is visible to students and
co-teachers.

## History and the "not always together" objective

Every saved chart is versioned; the section keeps a rolling window (about the last ten).
From that history the adjacency ledger knows which pairs have been neighbors too often
lately. The solver uses that to rotate neighbors over time, and CE can point out
"you've paired these two seven of the last eight charts, keep it?" rather than silently
repeating.

## Setups (RoomState)

A teacher builds their room a few ways once (Testing, Pairs, 4-tops), then taps between
them. Each setup owns its furniture and its own soft-objective profile:

- Testing leans toward spreading everyone out.
- Pairs leans toward mentor pairings.
- 4-tops leans toward mixing tiers.

Shared across every setup (section-level): roster, grouping dimensions, relationships
including accommodations and keep-apart, and the adjacency ledger. A student's
accommodations follow them across setups, so switching never resets someone's needs. New
setups can start empty, seed from another setup (same people, reshaped), or auto-arrange
from the profile.

## Solver priority

Lexicographic. Hard first and inviolable; soft traded off below.

1. Hard: accommodations (front / near-teacher) and hard separations. If a request is
   infeasible, CE says so instead of quietly breaking it.
2. Soft, requested: mentor pairings.
3. Soft, dimension: mix academic tiers, spread distractibility.
4. Soft, novelty: rotate neighbors against the ledger.

## Printables

One layout renders for several readers, and orientation is a per-printable choice:

- Student-facing chart (defaults to the entering / mirror-flipped view).
- Desk name cards / tents, printed in seating order.
- Sub packet (teacher-view chart plus a plain roster, fully offline).
- Blank planning copy.
- Optional "how to arrange the desks" diagram for a setup, useful when students move their
  own desks.

The teacher-view vs entering-view flip matters: print the wrong orientation and every
student sits on the wrong side. Output is PDF via installed Edge (userspace, fits the
no-admin ZIP delivery constraint).

## MCP surface

One pseudonymized read tool:

```
get_seating_context(section) -> {
  students:    [ { pseudonym, academic, distractibility, interests } ],
  constraints: [ { type, students:[pseudonym], strength, reason, region } ],
  adjacency:   [ { pair:[pseudonym, pseudonym], timesAdjacent, ofLastN } ]
}
```

The model reads that, proposes a seat map keyed by pseudonym and seat id, and hands it back
to CE to de-pseudonymize and apply locally. `note` and free-text reasons never enter the
payload.

## Local vs Canvas

- Local only: rooms, setups, assignments, relationships, accommodations, the ledger, and
  distractibility-style axes.
- Canvas (via CM/CE only): group sets for the dimensions a teacher chooses to sync, such as
  academic tier and interests.

## Suggested build order

1. Room builder + manual seating + printables. No solver, no lenses. This alone already
   beats a standalone tool for a Canvas teacher.
2. Relationships (accommodations, pair, separate) and the local solver honoring the
   priority order.
3. Grouping dimensions and lenses, including the CM/CE group-set write path.
4. History, the adjacency ledger, and the novelty objective.
5. AI-proposed arrangements over the pseudonymized MCP read tool.

## Open questions

- Neighbor-graph details for mixed row blocks (how far front/behind still counts).
- Infeasibility UX when hard constraints can't all be satisfied at once.
- Whether the CM/CE group-set write reuses the existing grade/comment mutation contract or
  needs its own.
