# Authoring documentation consolidation — implementation brief

Status: approved for implementation (2026-07-23). Planner: Codex. Implementer: one executor.

## Objective

Make `api/default_docs/` the one immutable, shipped repository source for all authoring
documentation distributed to teachers. A teacher workspace receives a one-way seed and
may be customized freely; it is never an upstream source and rebuilds never overwrite it.
Remove the `AI-TA` and `FeedbackExpert` product names from teacher-facing surfaces.

## Teacher-visible result

- The workspace uses `Library/AI Authoring/`, not `Library/AI-TA/`.
- It contains short, plainly named authoring guides and the paste-ready authoring files.
- “AI Authoring” is a local collection of files for use with a teacher's chosen assistant,
  not a Canvas Expert app or AI service.
- Existing teacher changes are preserved during the one-time folder rename: copy/merge
  `Library/AI-TA/` into `Library/AI Authoring/` without overwriting an existing destination
  file, then leave the old folder intact with a short retirement notice. Do not delete or
  modify teacher-authored content.

## Locked source layout

`api/default_docs/AI Authoring/` is the sole repository source root. It contains:

- `START HERE - Canvas Expert.txt` — concise teacher orientation.
- `Author a Quiz (QuizForge).txt`, `Author an Assignment (AssignmentForge).txt`,
  `Author a Page (PageForge).txt`, `Author a Rubric (RubricForge).txt` — canonical
  paste-ready authoring prompts, including each Forge contract.
- `Reference/` — canonical supporting examples/modules needed by those prompts, including
  the QuizForge sample and ELA question-design module.
- `MagicSchool Toolkit/` — short setup recipes only. It must refer to the canonical
  authoring prompt and `Reference/` files; it may not contain copied instruction or
  knowledge files.

The `api/default_docs` copies are authoritative text. There is no separate `LLM_Modules/`
source tree and no generated-wrapper source that can drift from them.

## Required implementation

1. Move the live Forge contracts, teacher explainer, quiz example, ELA module, stimulus
   reference, and TAForge material from `LLM_Modules/` into the locked default-doc layout.
   Retire `LLM_Modules/` only after every live reader is repointed and tests pass.
2. Remove the duplicated MagicSchool `— INSTRUCTIONS` and `— KNOWLEDGE` files. Update its
   setup recipes and the AI Expert page so downloads point to their one canonical file.
3. Replace the `ai_ta` product vocabulary in user-facing routes, templates, headings,
   workspace folder names, and help text with `AI Authoring`. Internal Python symbols may
   remain temporarily only where a rename would be unrelated; no visible text or path may
   expose `AI-TA`.
4. Repoint all contract readers to `api/default_docs/AI Authoring/`: the AI-authoring
   library builder, the MCP `get_authoring_contract` tool, `/api/download-contract`, and
   their tests. They must return the exact canonical files, not regenerated equivalents.
5. Update source comments and developer documentation that claim `LLM_Modules` is
   canonical. Engine-specific documentation remains under `engine/docs/`; this slice does
   not fold the imported engine's documentation into `docs/`.
6. Do not change Forge schemas, validators, Canvas write behavior, privacy boundaries, or
   unrelated workspace structure. Do not edit user workspace content except the explicit
   non-overwriting migration above.

## Preflight and stop conditions

- Before editing, confirm every `LLM_Modules` reader with `rg` and add it to the brief's
  implementation report.
- Stop RED if a reader requires an authoring file not listed above, if a path move changes
  validator behavior, or if preserving a teacher customization requires overwrite/delete.
- Stop YELLOW if the current workspace migration cannot be covered by focused tests.

## Acceptance criteria

1. `LLM_Modules/` no longer exists and `rg "LLM_Modules|AI-TA|FeedbackExpert"` finds no
   teacher-visible string or live path reference outside historical/retired records.
2. Each Forge contract has exactly one repository file under `api/default_docs/AI Authoring/`.
   MCP and download endpoints return that file's bytes exactly.
3. No `MagicSchool Toolkit` instruction or knowledge file duplicates a canonical prompt or
   reference file; setup recipes retain a usable teacher path to those files.
4. A fresh workspace receives `Library/AI Authoring/` and no `Library/AI-TA/` directory.
   An existing workspace migration preserves destination files and never overwrites a
   teacher-edited one.
5. Affected rendered routes—AI Expert, Settings, and Course Expert—show “AI Authoring,”
   have working download/copy controls, and add no browser-console errors.
6. Named gate: `py -m pytest api/tests/test_ai_ta.py api/tests/test_workspace.py
   api/tests/test_mcp_server_tools.py api/tests/test_route_contract.py
   api/tests/test_webui_template_contracts.py`. Add focused migration/endpoint assertions
   where the existing tests do not cover the acceptance criteria.

## Execution result

Status: GREEN. Implemented as specified; no stop conditions triggered.

### Preflight — confirmed `LLM_Modules` readers (before editing)

Live (executed) readers, all repointed to `api/default_docs/AI Authoring/`:
- `api/mcp_server/tools.py` (`get_authoring_contract`'s `_CONTRACT_FILES` + path build)
- `api/webui/ai_ta.py` (`DEFAULT_AI_TA_DIR`, former `CONTRACT_FILES`/`QUIZFORGE_EXPLAINER_PATH`
  wrapping code — removed, not repointed; see below)
- `api/webui/routes/library.py` (`/api/download-contract`'s path build)

Everything else that matched `LLM_Modules` was prose/comments/docstrings (`AGENTS.md`,
`docs/mcp-server.md`, `docs/reference/author-and-stage-overview.md`,
`docs/reference/course-expert-module-map.md`, `docs/reference/settings-module-map.md`,
`api/README.md`, `api/rubrics/README.md`, `api/webui/README.md`, `api/webui/af.py`,
`api/webui/pf.py`, `api/webui/rf.py`, `engine/validation/rules/fairness_rules.py`,
`engine/rendering/correction_doc/renderer.py`, `engine/tests/unit/test_meta_answer_detection.py`)
— all updated to cite the new location, except `engine/docs/ARCHITECTURE.md` and
`engine/docs/AGENT_MAP.md`, left untouched per this brief's own engine-docs exclusion.

### Decisions made for points the brief left open

1. **No separate wrapper-generation code.** The brief's "no generated-wrapper source that
   can drift" ruled out keeping `ai_ta.py`'s old approach (read raw `LLM_Modules/*_Base.md`,
   wrap with a paste-ready preamble at seed time). The wrapped "Author a ...txt" files are
   now themselves the static, hand-maintained canonical files; `ai_ta.py` only copies the
   default tree into a workspace (seed-once) and generates the per-rubric "Score with -
   ...txt" files, which must stay dynamic since they depend on the teacher's own rubric
   library. This is why acceptance criterion 2 holds trivially: both readers open the same
   file.
2. **Two of the four checked-in wrapped Forge files were stale**, predating later edits to
   their `LLM_Modules` source (QuizForge was missing a "keep the tier out of the title"
   section; AssignmentForge was missing a "label is the private readiness identity"
   section) — `_write_text_if_missing`'s seed-once semantics meant they were never
   regenerated. Both were rebuilt fresh from the current contract text before the move.
   `QuizForge_Explainer.txt` was the opposite case — stale/superseded relative to the
   already-current, hand-edited "START HERE" file — so it was dropped rather than used as
   a source; the current START HERE content is what carried forward (retitled, unaffected
   otherwise).
3. **TAForge** (mentioned in item 1's prose but not in the locked layout's example list)
   placed as a fifth top-level `Author a TA (TAForge).txt`, matching the pattern of the
   other four and `ai_ta.py`'s pre-existing (if never-shipped) `CONTRACT_FILES` entry for
   it. Freshly generated (no prior checked-in copy existed).
4. **Essay Scorer's toolkit INSTRUCTIONS file** is not a duplicate of anything canonical
   (no other file holds essay-scoring instructions), so it stays exactly where it was,
   generated by `ai_ta.py` directly into `MagicSchool Toolkit/` — this doesn't conflict
   with "no copied instruction/knowledge files," since it was never a copy.
5. **Stale duplicate found and removed in passing**: the repo had both a code-generated
   "About This Folder.txt" and a checked-in `_about this folder.txt` with contradictory
   claims about overwrite behavior. Consolidated into one static
   `About This Folder.txt` (the accurate description), matching the spirit of this brief
   even though the brief didn't name it explicitly.
6. `/api/download-contract`'s public `?name=` values (`QuizForge_Base`, etc.) were kept
   unchanged for URL stability; only the internal file each maps to moved. Media
   type/download filename corrected from `.md`/`text/markdown` to `.txt`/`text/plain` to
   match the actual file.
7. Route paths (`/api/ai-ta/*`) and internal Python symbols (`ai_ta.py` module name,
   `ai_ta_dir()`, `list_ai_ta_files()`, `AI_TA_PERSONA_DEFAULT`, etc.) were left as-is per
   "internal Python symbols may remain temporarily" — none of these are teacher-visible
   strings or paths. Every literal `"AI-TA"` string that produces a teacher-visible path or
   UI string was changed to `"AI Authoring"`.

### Workspace migration

Added `workspace._migrate_ai_ta_library()`, called from `ensure_workspace()` before
`Library/AI Authoring` is seeded from `default_docs` (ordering matters: migrating first
means a teacher's old file wins over a fresh default with the same name). Copies
`Library/AI-TA/*` into `Library/AI Authoring/` non-destructively (skip-if-exists,
recursive), then writes a one-time retirement notice inside the old folder. Never deletes
or edits anything in `Library/AI-TA/`. Idempotent. Covered by
`test_ensure_workspace_migrates_ai_ta_into_ai_authoring_without_overwriting` and
`test_ensure_workspace_fresh_install_has_no_legacy_ai_ta_folder` in `test_workspace.py`.

### Test gate

`py -m pytest api/tests/test_ai_ta.py api/tests/test_workspace.py
api/tests/test_mcp_server_tools.py api/tests/test_route_contract.py
api/tests/test_webui_template_contracts.py` — all green. Full `api/tests` + `engine/tests`
suite also green (1403 passed, 1 skipped, skip pre-existing/platform-gated and unrelated).
Added: two workspace migration tests (above), two byte-exact contract tests in
`test_mcp_server_tools.py` covering acceptance criterion 2, and updated the `AI-TA` ->
`AI Authoring` literals in `test_ai_ta.py` / `test_workspace.py` / `test_beta075_runtime.py`.
`test_route_contract.py` and `test_webui_template_contracts.py` needed no changes — route
paths/methods and their existing assertions are unaffected by this consolidation.

Manually verified live: started the web UI and hit `/ai-expert`, `/settings`,
`/course-expert` (200 OK, "AI Authoring" rendered, no stale "AI-TA" text, no server
exceptions), `/api/download-contract?name=QuizForge_Base` (returns the wrapped canonical
text), and `POST /api/ai-ta/rebuild` (still seeds/rebuilds successfully).

### Final acceptance-criteria check

1. `LLM_Modules/` removed; repo-wide `rg "LLM_Modules|AI-TA|FeedbackExpert"` sweep confirmed
   clean outside `engine/docs/` (excluded by this brief), this brief itself,
   `docs/reference/powergrader-scoring-map.md` (already-historical), and legitimate
   references to the legacy folder name in the new migration code/tests (which must name
   what they migrate *from*).
2. Each Forge contract has exactly one file under `api/default_docs/AI Authoring/`; MCP and
   download endpoints proven byte-exact against it.
3. MagicSchool Toolkit no longer duplicates any canonical prompt/reference file; all five
   SETUP recipes retain a working relative path to the real file.
4. Fresh workspace gets `Library/AI Authoring/` only; existing-workspace migration preserves
   teacher edits and never overwrites.
5. AI Expert, Settings, and Course Expert all show "AI Authoring" (or, for Course Expert,
   already-neutral copy) with working controls and no rendering errors.
6. Named test gate green (see above).
