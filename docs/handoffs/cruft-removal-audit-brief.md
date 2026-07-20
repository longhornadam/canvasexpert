# Cruft-removal & de-duplication audit — brief for a fresh senior session

> **SENIOR INVESTIGATION, not a locked executor brief.** This is a hunting license with
> leads, method, and guardrails — not a mechanical checklist. Read `AGENTS.md`, this file,
> and the contracts named below. Produce a **ranked excision list with evidence before
> cutting anything.**

## Why this exists

The codebase grew from ~35k to ~126k lines in about two weeks of heavy AI-assisted
building. A lot of real capability landed — but rapid AI-built code reliably accretes
overbuild, speculative generality, and duplicated effort. 1.0-beta is code-complete and
accepted (`docs/reference/1.0beta-acceptance-record.md`); the goal now is to **cut fat
without losing behavior**, with a particular eye on **CanvasExpert pieces talking to both
CanvasMirror AND live Canvas when only one is needed.**

## Method (deletion-first, contract-guided, test-guarded)

1. **The 1129 tests are the safety net — lean on them, don't add more.** After every
   excision: `py -m pytest api/tests` + `py -m pytest engine/tests` must stay green. Green
   after deletion = safe. If a test exists *only* to cover deleted cruft, delete it too. Do
   NOT build synthetic harnesses or new test infra to gain confidence — the suite is the bar.
2. **Use the machine contracts as the "what's actually used" oracle**, the way Batch 8 used
   them to prove 4 adapters were dead:
   - `docs/contracts/canvas-transport-owners.json` + `test_canvas_mutation_ownership.py`
   - `api/tests/test_transport_ownership.py` (the direct-HTTP owner allowlist)
   - `docs/reference/mutation-reconciliation-map.md`, `canvas-read-spine-contract.md`
3. **Verify against code, never doc prose.** This project's docs have repeatedly been stale
   (the reconciliation map mislabeled curves; the spine status column lied about batch
   completion). Trust `rg` + tests, not comments.
4. **Delete atomically** (code + its test + its contract entry), like the Batch 8 retirement.
5. **Prefer deletion over refactor.** If it's genuinely used, leave it. If it's dead or a
   duplicate path, cut it. Don't gold-plate replacements.

## Leads, highest-confidence first

### 1. CanvasMirror-vs-live duplication (the named target)

The spine §21 open-risk list already names these — verify each against code and decide
migrate-to-mirror / downgrade-to-fallback-only / delete:
- **#5 duplicate structure acquisition** — Course Catalog and the private mirror
  independently fetch assignments.
- **#6 Roster/Course Info bypass** — `api/webui/routes/courses.py` still fetches users,
  sections, groups, memberships, modules, assignments **live** (with N+1 group reads) despite
  mirror scopes existing.
- **#7 Create picker bypass** — module/assignment-group pickers have direct live routes.
- **#10 Student Report/portfolio bypass** — `api/report_local_reads.py` is migrated, but
  `api/portfolio_service.py` and `api/student_packet.py` keep `requests.Session()` live
  fallbacks. **Check whether those fallbacks are ever exercised or are dead.**
- **Concrete entry list:** `api/tests/test_transport_ownership.py` allowlists exactly the
  ~15 files doing direct HTTP. The webui routes on that list doing *reads*
  (`courses.py`, `reports.py`, `roster_canvas.py`) are the audit targets. For each read: is
  it redundant with a `read_service` scope? If yes, migrate + delete the live path. If it's a
  genuine write-decision-boundary read (design law 5.7) or a real fallback, keep it and say so.

### 2. Dead code beyond the four retired adapters

Batch 8 proved dead code hides in plain sight. Hunt more:
- Registered/exported symbols with **no non-test producer or consumer** (e.g., `known_kinds()`
  has no production caller; the generic `/api/operations/{kind}/prepare` accepts any KIND).
- `api/webui/mirror_reads.py` is an explicitly-annotated compatibility shim slated for removal
  once the routine/sweep/curve read call sites migrate — **check if they can migrate now**,
  then delete the shim + its test.

### 3. Overbuilt abstractions / speculative generality

- The **bounded coordinator** (`api/mirror/coordinator.py`, 346 lines + telemetry, self-rated
  "high risk"): does the full priority/dependency/coalescing/cancellation machinery earn its
  keep, or would a simpler debounced per-course refresh do? Weigh it against how it's actually
  invoked.
- The **operation-ledger content-adapter decomposition** and the **webui presentation-system
  template-family migration** — evaluate whether the abstraction layers pay for their
  indirection.
- Smell signals: single-implementation "registries," one-caller "frameworks," config
  parameters never set to anything but the default, layers that only forward.

### 4. Duplicate read/helper layers

Three read layers coexist: `mirror_reads.py` (shim) + `mirror/read_service.py` +
`mirror/queries.py`. And multiple "get submissions" paths (mirror / live / focused /
powergrader). Map them; collapse redundancy.

### 5. Test cruft (last, and carefully)

After code excision, prune tests that only covered deleted paths, and the ad-hoc per-file
fake-Canvas scaffolding (`_ln_get`/`_ln_send` repeated across dozens of files) where the
covered code is gone. **Keep the contract/architecture tests** (mutation-ownership,
transport-ownership, read-spine, privacy scan, none-label guard) — those are the net that
makes aggressive removal safe.

### 6. Follow the growth

`git log --stat` the two-week window and rank files/dirs by lines added. The biggest
additions — the redesign (`canvasexpert-redesign-*`), `operation_ledger`, `powergrader`,
the webui presentation system, the coordinator — are the richest hunting grounds.

## Guardrails

- Keep both suites green after every change; a red suite means stop and reassess.
- Never remove a genuine write-decision-boundary live read (design law 5.7) or a
  security/fail-closed guard (vault conflict, disposable-root cleanup, student-free
  projection boundaries). Verify redundancy first.
- Preserve the accepted 1.0-beta behavior and the machine contracts; if a removal would
  change a contract, that's a senior decision, not a mechanical cut.

## First move

Produce two artifacts before cutting: (a) a **dead-symbol reachability scan** (exported/
registered symbols with no non-test caller), and (b) a **CanvasMirror-vs-live duplication
inventory** (every live read with whether an equivalent mirror scope exists). Rank by
lines-removed-per-risk, then excise top-down, suite-green at each step.
