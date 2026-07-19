# Establish a machine-checked Canvas mutation ownership boundary

> **DEEPSEEK EXECUTION AUTHORITY.** Read `AGENTS.md`, this file, and only the references
> routed below. Do not read `NEXT_BATCH.md`, `HANDOFF_TEMPLATE.md`, or `archive/`.

Status: **READY**

Risk: **medium** - no runtime behavior changes, but an incomplete ownership contract would hide
beta-blocking write/reconciliation gaps.

Depends on: commit `047e882` (accepted 05 MCP typed local reads)

## Teacher-visible result

No UI change. Every outbound mutation call becomes machine-accounted with its owner, transport,
affected local scopes, and present reconciliation state, giving the senior a bounded source for
the remaining Batch 7 implementation briefs without rereading the repository.

## Acceptance criteria

- [ ] A strict, student-free `docs/contracts/canvas-transport-owners.json` lists every detected
      non-test mutation call by stable relative path + qualified symbol + call form, with
      classification, affected scopes, current reconciliation (`targeted|invalidate|none|n/a`),
      and a concise exception/gap reason.
- [ ] `api/tests/test_canvas_mutation_ownership.py` uses Python AST/source inspection to fail on
      an unlisted `_canvas_send`/`canvas_send`, HTTP `post|put|patch|delete`, generic request with
      a mutation method, upload POST, or specialized native grader mutation under `api/`.
- [ ] The test also fails for a listed owner no longer present, duplicate owner keys, unknown
      classifications/scopes/states, absolute paths, URLs, secrets, or student-identifying data.
- [ ] `docs/reference/mutation-reconciliation-map.md` groups the machine contract into the next
      exact vertical families and names which existing paths are already covered versus gaps;
      it does not call any gap GREEN.
- [ ] Diagnostics, OpenRouter/external-AI calls, generic Canvas transport internals, uploads, and
      specialized New Quiz transport remain explicitly classified rather than silently excluded.
- [ ] The named acceptance gate passes and the executor reports counts by classification and
      reconciliation state.

## Explicit non-goals

- Implementing reconciliation, changing transports, deleting shims, editing runtime modules,
running Canvas, or declaring Batch 7/8 complete.

## Locked decisions

- The JSON contract is the machine authority; the Markdown map summarizes/groups it and links
  back rather than duplicating call-level facts.
- Key entries by repo-relative path and qualified enclosing symbol/call form, never line number.
- Scan production Python under `api/`; exclude `api/tests/`, generated/cache files, and vendored
  dependencies only. Classify non-Canvas writes explicitly as `external` or `local`, not gaps.
- Allowed affected-scope vocabulary: `catalog.assignments`, `catalog.modules`,
  `catalog.assignment_groups`, `private.assignments`, `private.submissions`,
  `private.submission_comments`, `private.roster`, `private.groups`, `gradebook.late_policy`,
  `new_quiz.metadata`, `new_quiz.responses`, `focused_evidence`, `none`, `unknown`.
- `unknown` is allowed only with reconciliation `none` and must become a named next-batch gap.

## Scope

- `docs/contracts/canvas-transport-owners.json` (new)
- `docs/reference/mutation-reconciliation-map.md` (new)
- `api/tests/test_canvas_mutation_ownership.py` (new)

## Read only these references

- `AGENTS.md`; this promoted brief; `TOOLS.md`
- `docs/reference/canvasmirror-1.0beta-information-spine.md`: §14.2, Former Program 9, and Former
  Program 10 only
- `docs/reference/operation-ledger-module-map.md`
- production files returned by the preflight searches, one owning symbol at a time

Do not read archived handoffs, whole adapters without a matched symbol, or the whole spine.

## Preflight - stop if these facts are false

```powershell
rg -n "_canvas_send\(|canvas_send\(" api -g "*.py" -g "!api/tests/**"
rg -n "requests\.(post|put|patch|delete)|\.request\(" api -g "*.py" -g "!api/tests/**"
rg -n "\.post\(|\.put\(|\.patch\(|\.delete\(" api/powergrader api/operation_ledger -g "*.py"
```

- Every result can be assigned to a qualified symbol and classified without executing it.
- If dynamic dispatch prevents reliable detection, return RED with the exact pattern.

## Named acceptance gate

```powershell
py -m pytest api/tests/test_canvas_mutation_ownership.py api/tests/test_operation_ledger.py -q
```

- Mutation-scan tests must include synthetic unlisted-call and stale-listed-owner failures.
- No broad suite; zero runtime source files may change.

## Stop conditions

- **RED:** the scanner cannot account for a dynamic/native mutation family without false safety.
- **YELLOW:** one call's affected scope or reconciliation state is genuinely ambiguous; classify
  it `unknown/none`, name it in the map, and request the senior decision.

## Execution result

Record traffic light, three changed files, gate/counts, totals by classification/state, exact
unknown gaps, deviations, unresolved decisions, and commit hash if created.
