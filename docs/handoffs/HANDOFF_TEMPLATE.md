> **SENIOR-ONLY TEMPLATE — NOT AN IMPLEMENTATION BRIEF.** Copy and complete this as
> `docs/handoffs/CURRENT.md`; an executor must never implement directly from this file.

# <One vertical teacher-visible improvement>

Status: **<READY | ACTIVE | YELLOW; decision needed | RED; stopped | GREEN; completed>**

Risk: **<low | medium | high>** - <one sentence naming the actual boundary>

Depends on: <accepted commit/current `dev`, or nothing beyond current `dev`>

Keep this brief slice-specific, normally under 100 lines. Record decisions here; link
durable contracts and route cards instead of copying their narrative. A long reference
must be routed by exact heading/numbered section, never assigned wholesale.

## Teacher-visible result

<What the teacher sees or is protected from. For invisible safety/performance work, name
the observable evidence.>

## Acceptance criteria

- [ ] <Independently checkable outcome the senior will use to accept this brief.>
- [ ] <Required safety/compatibility fact, if applicable.>
- [ ] The named acceptance gate below passes.

The executor reports evidence; it does not redefine, narrow, or self-accept these criteria.

## Explicit non-goals

- <Adjacent behavior deliberately not changed, and its current owner/future decision.>

## Locked decisions

- <Exact behavior, owner, schema allowlist, and live-vs-local boundary.>
- <Compatibility or vocabulary decision the executor must not rediscover.>
- <Privacy/write rule, if applicable.>

## Scope

- <Exact files/symbols or narrowly bounded ownership areas allowed to change.>

## Read only these references

- `AGENTS.md`
- <small module route card or exact contract/reference heading>
- <exact implementation/test files needed after preflight>

Do not read: `docs/handoffs/archive/`, unrelated module maps, or whole vision documents.

## Preflight - stop if these facts are false

```powershell
<small rg commands proving named insertion points on current dev>
```

- <Expected fact, one per assumption.>

If any fact is false, return RED without implementation changes.

## Known baseline (only when relevant)

`<known HEAD>`: `<exact broad/focused command>` -> `<pre-existing result and reproduction state>`.
This brief neither fixes nor re-litigates that baseline; report only a change to it.

## Named acceptance gate

```powershell
<the focused test set and any rendered/behavior check required to accept this brief>
```

- This named set is the slice gate. Run a broad matrix only when this brief explicitly
  declares an integration/release checkpoint.
- <Rendered-route, failure/idempotency/receipt, or performance evidence when required.>

## Stop conditions

- **RED:** <contradiction, missing seam, guardrail gap, or required contract expansion.>
- **YELLOW:** <one bounded decision/check that can be resolved without widening scope.>

## Execution result

<Executor records traffic light against the pre-authored acceptance criteria, commit hash if
any, changed files, named-gate commands/counts, deviations, and unresolved decisions. The
same compact report is returned to the senior.>
