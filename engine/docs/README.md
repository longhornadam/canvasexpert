# engine/docs/

Engine-layer reference docs. **Project orientation is the root `AGENTS.md`**
(one QuizForge JSON contract → three backends) — read that first.

## Canonical developer docs
- Architecture & data flow -> [`ARCHITECTURE.md`](ARCHITECTURE.md)
- File-by-file navigation -> [`AGENT_MAP.md`](AGENT_MAP.md)
- Live Canvas behavior and API limits -> [`../../api/README.md`](../../api/README.md)

## In this folder (engine/docs/)
- `ARCHITECTURE.md` - current engine architecture and boundaries
- `AGENT_MAP.md` - short navigation guide for engine-only agent work

## Engine spec-mode toggle
- `QUIZFORGE_SPEC_MODE=json` (default): JSON 3.0 pipeline via `engine/spec_engine` / `JsonImporter`.
- `QUIZFORGE_SPEC_MODE=text`: legacy TXT path (deprecated, backward-compat only).

## Other backends
- **QuizForge-API** (live Canvas push) is **not** part of the engine →
  [`../../api/README.md`](../../api/README.md).
