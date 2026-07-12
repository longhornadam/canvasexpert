# Documentation Index

This directory contains durable project documentation and senior-authored execution briefs.
For canonical AI-agent guidance and safety rules, read `../AGENTS.md` first.

## Sections

- `docs/contracts/` - durable data contracts and interface agreements.
- `docs/guides/` - durable usage, authoring, and workflow guidance.
- `docs/handoffs/` - active execution briefs plus the canonical brief template.
- `docs/handoffs/archive/` - completed or historical handoffs retained for reference.
- `docs/reference/` - stable reference notes and extracted facts.

Useful starting references for new debugging and refactor sessions:

- `docs/reference/course-expert-module-map.md` - Work tools push/download route, script, and template ownership map.
- `docs/reference/settings-module-map.md` - Settings route/script/config ownership map.
- `docs/reference/feedbackexpert-module-map.md` - Feedback tools route/pipeline/template ownership and privacy-sensitive routing map.
- `docs/reference/powergrader-module-map.md` - module ownership map, script load order, backend package routing, and current size snapshot.
- `docs/reference/gradebook-module-map.md` - Gradebook route/script ownership and feature routing map.
- `docs/reference/roster-module-map.md` - Roster route/script ownership and current hotspot map.

## Handoff Convention

The senior/orchestrator makes the difficult product and architecture decisions, then writes
one substantial brief from `docs/handoffs/HANDOFF_TEMPLATE.md`. One executor implements it:
Luna for established patterns, Terra for complex/guardrail-adjacent work, or an external
VS Code agent chosen by the user. Do not run planner/implementer/reviewer swarms.

Keep one active brief by default. The brief is the durable context checkpoint when a chat is
compacted, an executor changes, or work moves between Codex and VS Code. It must lock scope,
decisions, references, verification, and stop conditions before implementation starts. The
executor records its compact traffic-light result in that same brief before handback so test
evidence and current state do not exist only in chat.

Handoff closure belongs to the implementation batch. Archive a completed brief only when it
has continuing reference value; otherwise it may be deleted because Git preserves history.
Never create a separate acceptance or archive pass merely to move documentation.

Verification is risk-proportional. Focused checks are normal, affected subsystem checks are
used for shared changes, and full suites are reserved for integration/release boundaries or
genuinely cross-cutting/high-risk work. See `AGENTS.md` for the authoritative policy.
