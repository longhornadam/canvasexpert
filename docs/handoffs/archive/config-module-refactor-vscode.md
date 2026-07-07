# Handoff: Config Module Refactor For VSCode Agent

## Goal

Split `api/webui/config.py` (~1123 lines, 86 functions) into small single-concern
modules under `api/webui/config/`. Preserve every public function name, signature,
return shape, and import path — every consumer does `from .. import config` then calls
`config.get_token()`, `config.get_canvas_base()`, etc., and **none of that changes**.

This is a mechanical extract-and-re-export refactor. No behavior changes.

## Guardrails

- Read `AGENTS.md` first.
- Work on `dev`.
- Do not change any function signature, return type, or default value.
- Do not change the module docstring or any docstrings.
- Every existing import (`from .. import config`) must still work without changes.
- Every existing reference (`config.get_token()`, `config.get_canvas_base()`, etc.)
  must still resolve.
- Do not touch `LLM_Modules/*_Base.md`.
- Do not revert unrelated dirty worktree changes.

## Current shape

`api/webui/config.py` is one flat file with 14 sections demarcated by
`# ---` comment blocks:

1. **Imports + constants** (lines 1-222): `SERVICE`, `TOKEN_KEY`, `OPENROUTER_KEY`,
   `DEFAULT_OPENROUTER_MODEL`, `OPENROUTER_MODEL_PRESETS`, `CANVAS_BASE_DEFAULT`,
   `DOWNLOAD_ROOT_DEFAULT`, `CONFIG_PATH`, `SYNCED_KEYS`, plus private I/O helpers
   (`_machine_load`, `_workspace_load`, `_synced_state`, `_save_synced_key`)
2. **Canvas account** (lines 224-272): `get_canvas_base`, `set_canvas_base`,
   `get_token`, `set_token`, `token_is_set`, `get_download_root`, `set_download_root`,
   `save_canvas_account`
3. **OpenRouter** (lines 274-330): `get_openrouter_key`, `set_openrouter_key`,
   `has_openrouter_key`, `get_openrouter_model`, `set_openrouter_model`,
   `openrouter_model_presets`, `_openrouter_cost_tier`
4. **Workspace path** (lines 332-344): `get_workspace_path`, `set_workspace_path`
5. **Bookmarked courses** (lines 346-399): `saved_courses`, `active_courses`,
   `set_course_active`, `bookmark_course`, `remove_course`
6. **Gradebook Expert** (lines 401-436): `get_extra_time`, `set_extra_time`,
   `get_tier_tags`, `set_tier_tags`, `get_sweep_settings`, `set_sweep_settings`
7. **FeedbackExpert personas** (lines 438-650): `_persona_folder`, `get_persona_folder`,
   `_safe_persona_filename`, `_seed_persona_folder_once`, `_list_file_personas`,
   `list_personas`, `get_persona`, `save_custom_persona`, `remove_custom_persona`,
   `get_ai_ta_persona`, `set_ai_ta_persona`, `list_feedback_patterns`,
   `set_feedback_patterns`
8. **Calendars** (lines 652-687): `get_calendars`, `set_calendar`, `remove_calendar`,
   `clear_all_calendars`, `get_combined_calendar_for_range`
9. **Protected names** (lines 689-743): `list_protected_packs`, `set_pack_enabled`,
   `get_custom_protected_names`, `set_custom_protected_names`,
   `active_protected_names`, `LITERARY_PACKS`
10. **Runtime credential bundle** (lines 745-796): `resolve_env`
11. **Routines** (lines 798-815): `get_routine_states`, `set_routine_state`
12. **Student reports** (lines 817-870): `get_student_reports_root`,
    `set_student_reports_root`, `get_monitored_students`, `set_monitored_student`,
    `remove_monitored_student`
13. **Roster Console V2 — tier scheme** (lines 872-1060): `ROSTER_DEFAULT_TIER_SCHEME`,
    `_validate_tier_scheme`, `_normalize_tier_scheme`, `get_roster_tier_scheme`,
    `set_roster_tier_scheme`, `roster_tier_by_id`, `active_tier_ids`,
    `migrate_legacy_tier`
14. **Roster Console V3 — group scheme** (lines 1062-end): `DEFAULT_GROUP_LABELS`,
    `get_roster_group_scheme`, `set_roster_group_scheme`,
    `get_selected_group_category_id`, `set_selected_group_category_id`,
    `get_group_label`, `set_group_label`, `set_group_labels`,
    `compute_group_display`, `default_group_label`

## Proposed module layout

Create `api/webui/config/` as a package. Move each section above into its own module,
then have `config/__init__.py` re-export everything.

```
api/webui/config/
  __init__.py          # re-exports everything from all sub-modules (preserves import path)
  _io.py               # lines 1-222: imports, constants, private I/O helpers
  canvas.py            # lines 224-344: Canvas account, OpenRouter, workspace path
  courses.py           # lines 346-399: bookmarked courses
  gradebook.py         # lines 401-436: extra-time, sweep settings, tier tags
  feedback.py          # lines 438-650: personas, feedback patterns
  calendars.py         # lines 652-687: academic calendars
  protected_names.py   # lines 689-743: literary packs, protected names
  routines.py          # lines 798-815: routine states
  reports.py           # lines 817-870: student reports, monitored students
  roster.py            # lines 872-end: tier scheme, group scheme, student settings
```

**Important**: `_io.py` must export `_machine_load`, `_machine_save`, `_workspace_load`,
`_workspace_save`, `_synced_state`, and `_save_synced_key` so other config sub-modules
can import them.

## Circle import prevention

The ordering constraint is simple:

1. `_io.py` — no imports from sibling config modules. Only stdlib, `keyring`, `workspace`.
2. Everything else imports from `_io.py` (and possibly each other in limited cases).
3. `__init__.py` imports from all sub-modules and re-exports their public symbols.

There should be no circle because `_io.py` does not import from any sibling config module.

## Pattern

Every sub-module follows this pattern:

```python
"""One-line description."""
from ._io import _machine_load, _machine_save, _workspace_load, _workspace_save, \
    _synced_state, _save_synced_key

# (exact copy-paste of the section's code from config.py, unchanged)
```

`__init__.py` follows this pattern:

```python
"""QuizForge-API configuration.

Canvas base URL and the token remain machine-local. ... (full original docstring)
"""
from ._io import ...  # private — only needed internally
from .canvas import *
from .courses import *
from .gradebook import *
from .feedback import *
from .calendars import *
from .protected_names import *
from .routines import *
from .reports import *
from .roster import *
```

## Verification

After each file is created:

```powershell
py -m py_compile api/webui/config/__init__.py api/webui/config/_io.py api/webui/config/canvas.py
```

Before final handoff:

```powershell
py -m py_compile api/webui/config/*.py
py -m pytest api/tests/test_route_contract.py
py -m pytest api/tests
```

**No test changes are needed** — every reference to `config.xxx` resolves via `__init__.py`.

## Acceptance

- `from .. import config` still works everywhere.
- `config.get_token()`, `config.set_canvas_base()`, etc. still resolve.
- All ~229 tests pass unchanged.
- The original `api/webui/config.py` is removed (or kept as a thin re-export shim).