# Execution brief: <teacher-visible outcome>

Status: **ready for implementation**

Risk: **low | medium | high**

Executor: **Luna | Terra | external VS Code agent**

## Outcome

State the concrete teacher-visible result in two or three sentences. Explain why this
chunk is worth doing now.

## Locked decisions

List the architecture and product decisions already made by the senior. The executor
implements these decisions; it does not reopen them unless the repository contradicts
the brief.

## Scope

- Name the behavior to add/change.
- Name exact files, symbols, routes, or seams when known.
- Group related work that shares context and verification.

## Out of scope

- Name tempting adjacent work that is deliberately excluded.
- State whether migrations, compatibility removal, live probes, or new infrastructure
  are forbidden.

## Reference pattern and routing

- Existing implementation to follow: `<path>::<symbol>`
- Test pattern to follow: `<path>`
- Required durable contract/reference: `<path>`
- Read project-local `TOOLS.md` before using broad manual inspection.

Do not list unrelated background reading.

## Implementation requirements

Describe the substantial work in a short ordered list. Specify externally observable
behavior and safety boundaries, not line-by-line coding instructions.

## Verification

Choose evidence in proportion to the declared risk.

```powershell
# Focused command(s)
```

Add an affected subsystem suite only for shared behavior. Add the full API/engine suite
only when required by the risk or integration boundary. For browser work, name the exact
routes and interactions that require rendered verification.

## Stop conditions

Stop with RED rather than guessing if:

- A named insertion point or assumed interface is missing.
- Existing behavior contradicts a locked decision.
- The requested outcome requires a new public contract, persistence format, subsystem,
  or external transmission not authorized here.
- A credential, FERPA, live-write, or scheduled-write question is underspecified.
- An unrelated regression blocks completion.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to
the senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **not started | in progress | GREEN | YELLOW | RED**
- Commit hash, or state explicitly that changes are uncommitted
- Files changed
- Verification commands and pass/fail/skip counts
- Rendered routes checked, if applicable
- Deviations from the brief
- Remaining blocker or decision, if any
