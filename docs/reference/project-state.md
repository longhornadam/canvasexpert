# Project state and product principles

The single home for durable facts about *where Canvas Expert is* and *how that
constrains scope*. Read this before any decision about whether work is in-scope.
It exists so this context stops living in scattered chat threads and retired
handoffs and getting lost.

Keep it short and current. When a fact here changes (a launch date, a user
count), edit it — do not append a log.

## Status: pre-launch

Canvas Expert has **not launched**. It is weeks away from any real launch, and
nothing in it has been used in production.

## Userbase: 0 today, 1 for the first semester

- As of **2026-07-23** there are **0 users**.
- For the entire **first semester (roughly through December 2026)** the userbase
  is exactly **1 — the developer, who is also the first teacher**.
- The earliest additional users come no sooner than the following semester, and
  only after a deliberate decision to widen the pilot.

## What this means for scope (the load-bearing consequence)

Because no one has ever run this software, **no legacy state exists.** Therefore:

- **No migration code.** Do not write folder-rename migrations, dual-read
  shims, retirement notices, backward-compatibility mappings, or "URL stability"
  indirection. There is no old state to preserve. When a change is cleaner as a
  rename or restructure than as a migration, **take the clean break.**
- **No legacy records.** Retired names, deprecated features, and superseded
  layouts should be *deleted*, not carried with a compatibility note. Git history
  is the record.
- Anything guarding a pre-existing user's data or configuration is dead code for
  a population of zero — do not write it, and remove it when found.

## Standing product principles

These follow from the state above and from repeated direction; they are not
slice-specific.

- **One source of truth per artifact.** Never ship a static copy *and* a
  generated copy of the same thing (e.g. an authoring contract or a scoring
  skill). Pick the one canonical source; generate or read from it everywhere.
- **Lean, and don't reinvent harnesses.** The authoring contracts and teacher
  docs must be lean and un-wordy. Do not invent bespoke personas, "paste this
  whole file" framing, or step-by-step orchestration on top of assistants that
  already provide it (Claude Cowork, MagicSchool, ChatGPT Work). Rely on the host
  assistant's own conversational ability; ship the contract, not a harness around
  it.

See also `AGENTS.md` → *Lean engineering defaults* for the engineering-side
expression of the same instinct.
