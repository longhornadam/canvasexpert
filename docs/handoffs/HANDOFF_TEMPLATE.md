# <Slice name — one vertical teacher-visible improvement>

Status: **<QUEUED | READY | ACTIVE | GREEN; completed | RED; stopped>**

Risk: **<low | medium | high>** (one line saying why — FERPA persistence, write boundary,
shared coordinator semantics, or display-only)

Depends on: <prior slice name(s), or "nothing beyond current `dev`">

## Teacher-visible result

<2–5 sentences. What the teacher sees or is protected from after this slice. If the change
is invisible (safety/instrumentation), say what evidence proves it happened.>

## Read only these references

- <exact files and docs the executor may read>

<One line naming anything the executor must NOT read (stale handoffs, superseded docs).>

## Preflight — stop if these facts are false

```powershell
<rg commands proving each insertion point still exists on current dev>
```

Expected facts:

- <fact the rg output must show, one per assumption this brief depends on>

If any expected fact is false, return RED without writing code.

## Locked design for this slice

<The one projection/read/write decision this slice implements, plus exact symbols,
schema allowlists (fields permitted at rest / forbidden material), and behavior that must
remain live. Vocabulary note where relevant: state whether "pass" (current contract) or
"scope" (target contract) terms are in use.>

## Scope

- <in-scope changes>

## Out of scope

- <adjacent work explicitly deferred, with the slice or program that owns it>

## Verification

```powershell
<exact pytest commands>
```

- <rendered browser route checks with zero-new-console-error requirement, when a route
  changed>
- <performance evidence (request counts / durations), when the slice claims a perf effect>

## Stop conditions

- RED: <contradictory Canvas behavior, missing field, or failed preflight — stop, report>
- YELLOW: <ambiguity the executor may resolve only by narrowing scope, never by widening>

## Execution result

<Executor fills in: traffic light, commit hash, files changed, verification counts,
deviations from the brief, and any unresolved decision for the senior.>
