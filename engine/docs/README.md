# engine/docs/

Engine-layer reference docs. **Project orientation is the root `CLAUDE.md`**
(one QuizForge JSON contract → three backends) — read that first.

## Canonical developer docs (now live in `dev/`)
- Architecture & data flow → [`../../dev/ARCHITECTURE.md`](../../dev/ARCHITECTURE.md)
- File-by-file navigation → [`../../dev/AGENT_MAP.md`](../../dev/AGENT_MAP.md)
- Canvas behaviors found via the live API → [`../../dev/CANVAS_BEHAVIORS_REFERENCE.md`](../../dev/CANVAS_BEHAVIORS_REFERENCE.md)

## In this folder (engine/docs/)
- `JSON3_PRODUCTION_READINESS.md` — the JSON 3.0 spec-mode pipeline (`QUIZFORGE_SPEC_MODE`)
- `MIGRATION_GUIDE.md` — **historical**: the `Packager/quizforge/` → `engine/` restructure (Nov 2025)
- `VERIFICATION_CHECKLIST.md` — **historical**: migration sign-off snapshot (Nov 2025)
- `ARCHITECTURE.md` — redirect stub (canonical doc moved to `dev/`)

## Engine spec-mode toggle
- `QUIZFORGE_SPEC_MODE=json` (default): JSON 3.0 pipeline via `engine/spec_engine` / `JsonImporter`.
- `QUIZFORGE_SPEC_MODE=text`: legacy TXT path (deprecated, backward-compat only).

## Other backends
- **QuizForge-API** (live Canvas push) is **not** part of the engine →
  [`../../api/README.md`](../../api/README.md).
