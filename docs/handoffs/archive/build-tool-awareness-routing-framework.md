# Build Spec: Tool Awareness and Routing Framework

## Goal

Create a lightweight, reusable convention that helps Codex agents discover available tools, decide when to use them instead of brute-force LLM inspection, and document project-specific tools in a consistent way.

This first pass is documentation, templates, manifests, and routing rules only. Do not build the actual scraper, API inspector, or runtime framework in this task.

## Context

We want two layers:

1. A global Codex habit that applies across projects: use tools for retrieval, parsing, summarization, validation, and reduction before spending LLM context on large raw inputs.
2. A project-local convention for CanvasExpert: Canvas-specific tools and routing rules live in this repo and can evolve with it.

The system should be useful even while some tools are only planned.

## Files To Create Or Update

Create or update these files:

```text
CLAUDE.md
README.md
TOOLS.md
docs/
  README.md
tools/
  README.md
  manifests/
    repo-indexer.json
    test-failure-summarizer.json
    change-risk-summarizer.json
    canvas-docs-scraper.json
    canvas-api-inspector.json
  templates/
    tool-manifest.schema.json
    tool-readme-template.md
```

`CLAUDE.md` is the existing LLM guidance file for this repo. Treat it as the canonical project agent guidance unless the user explicitly asks to replace it. Do not create competing guidance that drifts from `CLAUDE.md`.

There is currently no obvious root table of contents for new LLM sessions. `CLAUDE.md` contains important orientation material, but future agents should not have to infer the repo map from scattered files. Add a concise root `README.md` and `docs/README.md` as part of this task, and make them point back to `CLAUDE.md` for authoritative agent guardrails.

## CLAUDE.md Requirements

Update `CLAUDE.md` as the repo's canonical LLM guidance file.

Add or update a short section explaining:

- Codex and other LLM agents should read `CLAUDE.md` before editing.
- `CLAUDE.md` should stay current when repo structure, handoff location, safety guardrails, major workflows, or tool-routing conventions change.
- Do not create parallel agent guidance files that conflict with `CLAUDE.md`.
- If another agent-specific file is introduced later, it should reference `CLAUDE.md` rather than duplicate policy.
- Project-local tool awareness now lives in `TOOLS.md` and `tools/manifests`.
- New active handoffs belong in `docs/handoffs`; completed or historical handoffs belong in `docs/handoffs/archive`.

If an `AGENTS.md` file is still desired for compatibility with agent tooling, keep it very small and make it point to `CLAUDE.md`, `TOOLS.md`, and `docs/README.md`. Do not duplicate the full guardrails or project orientation there.

## Repo Orientation Requirements

Create a root `README.md` that acts as a short table of contents for humans and LLM agents.

It should include:

- What CanvasExpert is
- The major top-level directories and what they contain
- Which files new agents should read first
- A clear pointer that `CLAUDE.md` is the canonical LLM guidance file
- Where handoffs live
- Where tool manifests live
- The basic run/test commands, or a pointer to `CLAUDE.md` if duplicating would drift
- The core safety guardrails at a high level: no secrets, no student data, no district-specific config, local-only app

Create `docs/README.md` as a documentation index.

It should include:

- `docs/contracts`
- `docs/guides`
- `docs/handoffs`
- `docs/handoffs/archive`
- `docs/reference`
- Guidance that active/new handoffs belong in `docs/handoffs`, while completed or historical handoffs belong in `docs/handoffs/archive`

Do not move archived handoffs in this task.

## Optional AGENTS.md Requirements

This repo currently uses `CLAUDE.md` for LLM guidance. `AGENTS.md` is optional and should only be created if useful for compatibility with tools that automatically look for it.

If created, `AGENTS.md` should be a thin pointer file:

- Read `CLAUDE.md` first.
- Read `TOOLS.md` before brute-force inspection of large inputs.
- Read `docs/README.md` to find handoffs, contracts, guides, and references.
- Preserve the safety guardrails in `CLAUDE.md`.

Do not duplicate the full project policy in `AGENTS.md`.

## Tool Awareness Policy Requirements

Add a section named `Tool Awareness Policy` to `CLAUDE.md`.

The section should explain that before using brute-force LLM inspection on large or repetitive inputs, agents should check for an available tool.

Use this check order:

1. Project-local `TOOLS.md`
2. Project-local `tools/manifests`
3. Global Codex skills/plugins, if available

Prefer tools for:

- Fetching or scraping documentation
- Searching or indexing the repository
- Parsing logs, test output, diffs, HTML, API responses, or structured data
- Validating schemas, links, dates, IDs, and generated artifacts
- Reducing large raw inputs into compact structured summaries

Use LLM reasoning for:

- Architecture decisions
- Tradeoff analysis
- Planning
- Reviewing summarized tool output
- Writing specs
- Explaining behavior

Add project-specific routing rules:

- For Canvas LMS API questions, check `canvas-docs-scraper` first.
- For Canvas course, assignment, module, quiz, rubric, user, or enrollment data, check `canvas-api-inspector` first.
- For local architecture questions, check `repo-indexer` first.
- For test failures, use `test-failure-summarizer` before reading raw logs.
- For large diffs or reviews, use `change-risk-summarizer` before reading full files.

## TOOLS.md Requirements

Create `TOOLS.md` as the human-readable tool registry.

It should include:

- Purpose of the registry
- How agents should choose tools
- Location of tool manifests
- Short list of available and planned tools
- Rule that tools should return compact structured output, not large raw dumps
- Rule that source URLs, file paths, commands, timestamps, and IDs should be preserved when relevant

Add entries for:

- `repo-indexer`
- `test-failure-summarizer`
- `change-risk-summarizer`
- `canvas-docs-scraper`
- `canvas-api-inspector`

Each entry should include:

- Use when
- Avoid when
- Expected output
- Current status

## Manifest Format

Create `tools/templates/tool-manifest.schema.json`.

Keep the schema simple and practical. The manifest fields should include:

```json
{
  "name": "string",
  "status": "available | planned | experimental",
  "purpose": "string",
  "use_when": ["string"],
  "avoid_when": ["string"],
  "inputs": {},
  "outputs": {},
  "command": "string|null",
  "source_of_truth": ["string"],
  "notes": "string"
}
```

It is acceptable to implement this as a real JSON Schema if straightforward. Otherwise, keep it as a clear documented template. Prefer valid JSON.

## Starter Manifests

Create five valid JSON manifests under `tools/manifests`.

### repo-indexer

Purpose: summarize repo structure, routes, components, services, API clients, models, and tests.

Use when:

- Discovering architecture
- Locating implementation points
- Finding call sites or imports
- Understanding project layout before making changes

Expected output:

- Compact map of files, symbols, routes, services, and tests
- Source file paths
- Any relevant commands used

Status: `planned`

### test-failure-summarizer

Purpose: run or parse test, lint, and typecheck output and return actionable failures only.

Use when:

- Tests fail
- CI logs are large
- The user asks what broke
- Raw command output is too noisy for direct LLM inspection

Expected output:

- Failing command
- File and line when available
- Failure message
- Likely affected area

Status: `planned`

### change-risk-summarizer

Purpose: summarize `git diff` by changed files, changed functions, risk areas, and recommended verification.

Use when:

- Reviewing large changes
- Preparing PRs
- Deciding which tests to run
- Assessing behavioral risk

Expected output:

- Changed files
- Public API or schema changes
- Behavioral risk notes
- Suggested tests or checks

Status: `planned`

### canvas-docs-scraper

Purpose: fetch or search official Canvas LMS documentation and return compact endpoint summaries.

Use when:

- Canvas API behavior is needed
- Endpoint paths, params, auth, pagination, or response shapes are needed
- Current official documentation should be verified

Expected output:

- Matching endpoints
- Required and optional params
- Response shape summary
- Source URLs
- Retrieval timestamp

Status: `planned`

### canvas-api-inspector

Purpose: inspect live or fixture-backed Canvas objects and normalize them into compact JSON summaries.

Use when:

- Course, module, assignment, quiz, rubric, user, or enrollment metadata is needed
- Relationships between Canvas objects matter
- Raw Canvas API responses are too large or noisy

Expected output:

- Normalized JSON summary
- IDs, names, dates, and relationships
- Source endpoint or fixture path
- Retrieval timestamp when live data is used

Status: `planned`

## tools/README.md Requirements

Explain the tool lifecycle:

1. Add a manifest under `tools/manifests`.
2. Mark status as `planned`, `experimental`, or `available`.
3. If implemented, include a command.
4. Keep output compact and structured.
5. Update `TOOLS.md` with a short human-readable summary.

Include this new tool checklist:

- Does this replace repeated LLM parsing or searching?
- Does it reduce large input to small structured output?
- Does it preserve source references?
- Does it have clear use and avoid rules?
- Is the command documented?

## tool-readme-template.md Requirements

Create a template future agents can copy when implementing a specific tool.

It should include sections for:

- Purpose
- Use when
- Avoid when
- Inputs
- Outputs
- Command
- Examples
- Output contract
- Failure modes
- Maintenance notes

## Acceptance Criteria

- `CLAUDE.md` identifies itself as the canonical LLM guidance file and tells Codex/LLM agents to keep it updated when project guidance changes.
- `CLAUDE.md` includes a tool-awareness and routing section.
- If `AGENTS.md` is created, it is a thin pointer to `CLAUDE.md`, `TOOLS.md`, and `docs/README.md`, not a competing policy file.
- Root `README.md` exists and gives new LLM sessions a concise repo table of contents.
- `docs/README.md` exists and indexes the docs directory, including `docs/handoffs`.
- `TOOLS.md` exists and describes the registry plus initial CanvasExpert routing rules.
- `tools/README.md` exists.
- `tools/templates/tool-manifest.schema.json` exists.
- `tools/templates/tool-readme-template.md` exists.
- Five starter manifests exist under `tools/manifests`.
- All manifests are valid JSON.
- No actual scraper or API implementation is required.
- No new runtime dependencies are introduced unless needed for JSON validation.
- Existing repo instructions are preserved.

## Non-Goals

- Do not build the Canvas docs scraper.
- Do not build the Canvas API inspector.
- Do not build a complex plugin system.
- Do not require agents to run every tool before thinking.
- Do not create large generated outputs.
- Do not introduce unnecessary dependencies.

## Suggested Verification

Run these checks from the repo root:

```powershell
Get-ChildItem -Recurse tools
Get-Content TOOLS.md
Get-Content CLAUDE.md
Get-Content README.md
Get-Content docs/README.md
python -m json.tool tools/manifests/canvas-docs-scraper.json
```

If Python is available, validate all manifests:

```powershell
Get-ChildItem tools/manifests/*.json | ForEach-Object {
  python -m json.tool $_.FullName > $null
  if ($LASTEXITCODE -ne 0) { throw "Invalid JSON: $($_.FullName)" }
}
```

## Implementation Guidance

Prefer clear docs and conventions over abstraction. The value of this task is the routing policy plus consistent metadata, not a runtime. Keep the language concise enough that future agents will actually read and follow it.
