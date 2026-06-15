# CLAUDE.md — Canvas Expert

Guidance for Claude Code and any AI agent working in this repo. Read this before editing.

## What this is

A teacher's toolkit for Canvas LMS, split out of the QuizForge monorepo. Two subsystems:

- **`api/`** — the **live, token-holding** app. A local FastAPI web UI (`py qf_ui.py` →
  `http://127.0.0.1:8765`) plus CLI scripts that push authored content to live Canvas
  courses (quizzes, assignments, pages, rubrics) and run Gradebook Expert (late sweeps,
  extensions, curves, submission downloads). Holds a Canvas access token. **Local-only,
  never served.**
- **`engine/`** — the **offline** quiz-rendering library (parse → validate → render →
  package to Canvas QTI / physical formats). No network, no token, no student data.

Authoring contracts live in **`LLM_Modules/*_Base.md`** (QuizForge, AssignmentForge,
PageForge, RubricForge). These are **canonical**. `api/` *consumes* them — never fork or
"fix" a contract by editing backend code. Detailed Canvas API facts and per-push behavior:
**`api/README.md`** (read it before touching push logic — it records hard-won live-probe
findings like the `result_view_settings` feedback rule and the New Quizzes 403/PAT limit).

**FeedbackExpert** (safe, honest LLM scoring/feedback) is built around the **Feedback Scoring
Contract** (`docs/contracts/feedback-scoring-contract.md`) — the LLM-agnostic, pseudonymized
JSON that any scoring tool emits and that Phase C (Push to Canvas) consumes. We deliberately do
**not** depend on an OpenRouter key; the contract is the seam that makes the LLM choice
irrelevant. Direction + status: `docs/handoffs/feedback-expert-next.md`.

## Guardrails (non-negotiable)

1. **Never commit secrets.** The Canvas token lives **only** in the OS credential store
   (`keyring`, Windows Credential Manager) for the Web UI, or in `api/.env` (gitignored)
   for CLI. A `.githooks/pre-commit` hook (wired via `core.hooksPath`) blocks the token
   pattern as a backstop — do not rely on it; don't paste tokens into tracked files,
   logs, test fixtures, or commit messages.

2. **Never commit student data (FERPA).** This app reads gradebooks, downloads
   submissions, and stores monitored-student notes. Student names, IDs, submission
   content, grades, and private notes must **never** land in the repo, a commit, a test
   fixture, or printed output that could be captured. Student exports go to the synced
   workspace / local output dirs (gitignored: `api/out/`, `api/temp/`, reports roots),
   in-tenant and FERPA-safe — never the repo. When in doubt, treat anything course- or
   roster-derived as PII.

3. **No district-specific config in the repo.** District URLs, calendars, rubric names,
   and the like belong in the **UI** and the **user-chosen synced workspace** (default
   `OneDrive\CanvasExpert\`, overridable; last-writer-wins `settings.json`) — not in source.
   The repo is district-agnostic: `CANVAS_BASE_DEFAULT` is empty (an empty base is the
   signal that first-run onboarding isn't complete); calendars are **data-driven** — the
   app lists whatever CSVs live in the workspace `Calendars` folder. The only calendar
   content shipped in-repo is a blank `calendar_template.csv` and a **fictional**
   `Summer_Session_Sample.csv` for testing. Do not reintroduce a real district's URL,
   calendar, or school/teacher name anywhere in source.

4. **Local-only, never exposed.** The Web UI binds `127.0.0.1`. Do not change the bind
   address, add public routes, or otherwise make this app reachable off the machine.
   Only `web/` is ever published (Netlify); nothing in `api/` is served.

## Ferrari / Toyota workflow

We split planning from implementation to save tokens, compute, and cost:

- **Ferrari = Claude Code (this tool).** Use for planning, architecture, security-
  sensitive changes, cross-cutting refactors, and anything touching the guardrails above.
- **Toyota = VS Code agents.** Use for well-scoped implementation where the plan is
  already clear.

**A plan handed off to a Toyota implementer must be self-contained** so the cheap agent
never has to round-trip back to the expensive planner. A good handoff states:

- Exact files to change (paths) and the function/class signatures involved
- The behavior change, with edge cases called out
- The test that must pass (or the new test to write) and how to run it
- Acceptance criteria + any guardrail that applies (token/FERPA/district/local-only)
- What **not** to touch (e.g. the `LLM_Modules` contracts)

If a change is security-sensitive or guardrail-adjacent, keep it in the Ferrari lane.

## Build / test / run

Windows + PowerShell. Python 3.13 (some artifacts show 3.14).

```powershell
# Run the Web UI (from repo root: "Open Canvas Expert.bat", or:)
cd api; py qf_ui.py            # http://127.0.0.1:8765

# Tests (no pytest config; run by directory)
py -m pytest api/tests
py -m pytest engine/tests

# Install deps
py -m pip install -r api/requirements.txt
```

## Onboarding wizard — implemented

The first-run experience (workspace-folder picker → Canvas URL → token → optional
calendar activation) is now implemented. See spec at
**`docs/handoffs/onboarding-wizard.md`** for details. An unconfigured app redirects
to `/welcome` automatically; a "Re-run setup wizard" link is available on Settings.

## Cleanup backlog

The district de-hardcoding / PII purge is **done** (hard-coded district URL, calendars, and
labels removed; the student-PII `default_docs/settings.json` deleted; rubric metadata
scrubbed; calendars made data-driven). Nothing outstanding here — keep guardrails #2 and #3
from regressing.
