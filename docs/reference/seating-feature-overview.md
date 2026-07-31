# Roster-First Seating feature overview

Status: concept / planning only (2026-07-21). This is a durable product reference,
not an execution brief. It defines ownership and safety boundaries for later, bounded
implementation slices; it does not authorize code changes.

## What it is

Seating is a local Canvas Expert surface where a teacher builds reusable classroom
layouts, seats their Canvas roster, reviews a proposed arrangement, and prints a chart.
The useful Canvas connection is the Roster-owned private student context: teacher-defined
seating supports, current score snapshots, and relationship constraints can inform a
seating or grouping proposal without exposing real student identities to AI.

## Ownership

Roster is the canonical owner of course- and section-scoped student context. Seating
consumes that context; it does not duplicate or redefine it.

Roster owns:

- Existing identity aliases and nicknames, all resolving to one vault identity and one
  pseudonym.
- The initial seating supports `front-row` and `near-teacher`, marked `required` or
  `preferred`.
- Separate private teacher notes and designated AI-context notes.
- A current, teacher-defined score matrix with named numeric columns. Values are current
  snapshots: there is no score history, normalization, or predefined proficiency model.
- Section-scoped `keep-apart` and `preferred-pair` relationships.

Names, aliases, identity records, private notes, relationship reasons, and all other
student context remain private local data. The UI must support bulk score entry.

## AI privacy boundary

The security line is that AI never receives real identity. Canvas Expert retains the
identity vault and is the only component that de-pseudonymizes or communicates with
Canvas.

Relevant MCP reads may include only pseudonyms, labeled current scores, structured
supports and relationships, and designated AI-context notes. Known names, preferred
names, nicknames, and aliases are scrubbed from included free text and map to the same
pseudonym. Private notes, raw identities, Canvas IDs, and accommodation reasons never
enter an MCP payload.

Pseudonymized educational information is not anonymous. A model may propose an
arrangement, but Canvas Expert validates every required constraint locally before a
teacher can apply it.

## Seating model

Seating owns the physical and presentational model only:

- A reusable physical room/layout describes the classroom and its seats.
- A named seating mode combines one layout with a strategy.
- Each mode has exactly one current assignment.

The core teacher workflow is: choose a mode, generate a temporary proposal, lock, swap,
or selectively reroll students, review the constraint results, apply it, and print. An
apply replaces that mode's current assignment. Undo is transient only; Seating retains no
chart history, assignment versions, usage tracking, or novelty data.

Strategies include testing, front-facing rows, buddy or mentor pairs, random trios, and
mixed or uniform four-person groups. A high score alone never establishes mentor
suitability; AI-context commentary may qualify that choice.

## Constraints and print views

Required supports and keep-apart relationships must be validated before a proposal is
applied. Preferred supports and preferred pairs inform an arrangement but may be reported
as unmet when the room or roster makes them impractical.

Teachers can manually seat students and print privacy-safe views. Student-facing output
uses only the information appropriate for students; teacher and substitute views remain
local. Printable rendering follows the established local physical-output path.

## Canvas groups

Canvas group-set import and export are a final, explicitly reviewed phase. Saving,
activating, printing, or applying a seating chart never mutates Canvas. Any later
import/export uses Canvas Expert's established trusted mutation path and requires the
teacher's explicit review and action.

## Explicit non-goals

- Seating, score, or assignment history.
- Assignment versioning, adjacency ledgers, usage tracking, rolling windows, or novelty
  objectives.
- A state-test, assessment-management, or persisted AI-derived proficiency ontology.
- Writing notes or seating supports to Canvas.
- Automatic Canvas group mutations.

## Suggested execution order

1. Complete the Roster-owned context: supports and notes, current score matrix, then
   relationships and the pseudonymized AI projection.
2. Build core Seating: reusable layouts, manual seating, one current assignment per mode,
   and privacy-safe print views.
3. Add local constraint-aware arrangement controls and validation.
4. Add academic and AI-assisted grouping, then the reviewed Canvas group integration.

Each implementation slice must be authorized by one direct brief with its exact scope,
acceptance criteria, verification gate, and stop conditions.
