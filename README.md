# CanvasExpert

CanvasExpert is a local teacher toolkit for Canvas LMS. It combines a token-holding
FastAPI web UI, Canvas push/download workflows, gradebook tools, pseudonymized feedback
pipelines, and an offline content rendering engine.

## Start Here

- `AGENTS.md` is the canonical AI-agent guidance file. AI agents should read it
  before editing and keep it current when repo structure, handoff conventions, safety
  rules, major workflows, or tool-routing conventions change.
- `TOOLS.md` is the project-local tool registry for deciding when to use tooling before
  spending LLM context on large raw inputs.
- `docs/README.md` indexes execution briefs, archived handoffs, contracts, guides,
  and durable reference notes.

## Repo Map

- `api/` - live, token-holding local app, FastAPI web UI, Canvas API workflows, grading
  and feedback tools. Keep local-only.
- `engine/` - offline quiz/content rendering library with no Canvas token and no student
  data.
- `LLM_Modules/` - canonical authoring contracts consumed by the app.
- `docs/` - contracts, guides, references, and senior-authored execution briefs.
- `tools/` - lightweight tool manifests, templates, and future helper tools for agent
  routing.
- `out/` - generated/local output area; do not treat as source.

## Handoffs

Canvas Expert uses a senior-design -> one-executor model. The senior makes architecture
decisions and writes one substantial execution brief in `docs/handoffs/`; one Codex or
external VS Code agent implements it and returns a GREEN/YELLOW/RED report. Active briefs
use `docs/handoffs/HANDOFF_TEMPLATE.md`. Historical handoffs live in
`docs/handoffs/archive/` and do not authorize new work.

Testing and review are proportional to risk. Focused checks are the default; full suites
are integration/release gates or evidence for genuinely cross-cutting/high-risk changes,
not a mandatory ritual after every edit. `AGENTS.md` is authoritative.

## Tool Manifests

Tool manifests live in `tools/manifests/`. They describe when agents should use a tool,
what output to expect, and whether the tool is planned, experimental, or available.

## Run And Test

See `AGENTS.md` for the authoritative run/test commands. Current local workflow is
Windows PowerShell with the `py` launcher.

## Safety Guardrails

Keep the Canvas token out of the repo, never commit student data, do not add
district-specific config to source, and keep the web UI bound to `127.0.0.1`.
