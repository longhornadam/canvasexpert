# Handoffs

This directory holds the **single active execution brief** while a batch of work is in
flight, per the workflow in [`../../AGENTS.md`](../../AGENTS.md).

It is empty between batches. The durable record of completed work is the Git history,
plus the design docs under [`../reference/`](../reference/) and
[`../contracts/`](../contracts/).

`senior level/` contains documents specifically for senior/coordinating agents that persist
across sessions, to be updated by the senior/coordinating agents.

Durable per-subsystem state — invariants, delivered batches, open decisions, known defects,
verification discipline — belongs in a route card under [`../reference/`](../reference/),
not in a brief. A brief is retired when its batch lands; the route card is what a new senior
reads first. See `../reference/writing-record-module-map.md` for the current example.