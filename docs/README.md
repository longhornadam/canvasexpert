# Documentation Index

This directory contains durable project documentation and implementation handoffs.
For canonical AI-agent guidance and safety rules, read `../AGENTS.md` first.

## Sections

- `docs/contracts/` - durable data contracts and interface agreements.
- `docs/guides/` - durable usage, authoring, and workflow guidance.
- `docs/handoffs/` - active or newly prepared implementation handoffs.
- `docs/handoffs/archive/` - completed or historical handoffs retained for reference.
- `docs/reference/` - stable reference notes and extracted facts.

Useful starting reference for new PowerGrader debugging sessions:

- `docs/reference/powergrader-module-map.md` - module ownership map, script load order, backend package routing, and current size snapshot.
- `docs/reference/gradebook-module-map.md` - Gradebook route/script ownership and feature routing map.
- `docs/reference/roster-module-map.md` - Roster route/script ownership and current hotspot map.

## Handoff Convention

New active handoffs belong in `docs/handoffs/`. After implementation, move historical
handoffs to `docs/handoffs/archive/` only when that archival work is explicitly in scope.
Do not move archived handoffs as part of unrelated documentation updates.
