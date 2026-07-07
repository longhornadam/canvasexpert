# Tools

This directory holds project-local tool manifests, templates, and future helper tools.
The initial framework is documentation-only; planned tools may not have implementations
yet.

## Available Helpers

```powershell
py tools/size_report.py
```

Reports `.py` and `.js` files at or above 300 lines, marking 500+ line files as
large. The report is advisory and exits successfully; it is meant to guide small
refactor slices, not block urgent fixes.

## Lifecycle

1. Add a manifest under `tools/manifests/`.
2. Mark status as `planned`, `experimental`, or `available`.
3. If implemented, include a command.
4. Keep output compact and structured.
5. Update `TOOLS.md` with a short human-readable summary.

## New Tool Checklist

- Does this replace repeated LLM parsing or searching?
- Does it reduce large input to small structured output?
- Does it preserve source references?
- Does it have clear use and avoid rules?
- Is the command documented?
