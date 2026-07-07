"""QuizForge-API configuration.

Canvas base URL and the token remain machine-local. Synced user content moves to
the OneDrive workspace when it exists. One-time migration copies the synced keys
into workspace/settings.json and leaves the old machine keys in place as dead
data so the two-PC last-writer-wins sync model stays simple.

This package re-exports all public configuration functions. Consumers import it
as `from .. import config` and call `config.get_token()`, etc. — no import-path
changes needed.
"""

# Re-export every public name from the sub-modules.
# The `_io` private helpers are imported only by sibling sub-modules, not here.

# --- canvas account, OpenRouter, workspace path, runtime env ---
from .canvas import (
    get_canvas_base, set_canvas_base,
    get_token, set_token, token_is_set,
    get_download_root, set_download_root,
    save_canvas_account,
    get_openrouter_key, set_openrouter_key, has_openrouter_key,
    get_openrouter_model, set_openrouter_model,
    openrouter_model_presets, _openrouter_cost_tier,
    get_workspace_path, set_workspace_path,
    resolve_env,
)

# --- bookmarked courses ---
from .courses import (
    saved_courses, active_courses,
    set_course_active, bookmark_course, remove_course,
)

# --- Gradebook Expert ---
from .gradebook import (
    SWEEP_DEFAULTS, TIER_NAMES,
    get_extra_time, set_extra_time,
    get_tier_tags, set_tier_tags,
    get_sweep_settings, set_sweep_settings,
)

# --- FeedbackExpert personas and patterns ---
from .feedback import (
    AI_TA_PERSONA_DEFAULT, DEFAULT_AI_DISCLOSURE_SIGNOFF,
    BUILTIN_PERSONAS, BUILTIN_PERSONAS_BY_ID,
    FEEDBACK_PATTERNS_DEFAULT,
    _persona_folder, get_persona_folder,
    _safe_persona_filename, _seed_persona_folder_once,
    _list_file_personas,
    list_personas, get_persona,
    save_custom_persona, remove_custom_persona,
    get_ai_ta_persona, set_ai_ta_persona,
    list_feedback_patterns, set_feedback_patterns,
)

# --- academic calendars ---
from .calendars import (
    get_calendars, set_calendar,
    remove_calendar, clear_all_calendars,
    get_combined_calendar_for_range,
)

# --- protected names ---
from .protected_names import (
    LITERARY_PACKS,
    list_protected_packs, set_pack_enabled,
    get_custom_protected_names, set_custom_protected_names,
    active_protected_names,
)

# --- routines state ---
from .routines import (
    get_routine_states, set_routine_state,
)

# --- student reports ---
from .reports import (
    STUDENT_REPORTS_DEFAULT,
    get_student_reports_root, set_student_reports_root,
    get_monitored_students, set_monitored_student, remove_monitored_student,
)

# --- Roster Console settings ---
from .roster import (
    ROSTER_DEFAULT_TIER_SCHEME, DEFAULT_GROUP_LABELS,
    get_roster_student_settings, set_roster_student_settings,
    update_roster_student_settings,
    _validate_tier_scheme, _normalize_tier_scheme,
    get_roster_tier_scheme, set_roster_tier_scheme,
    roster_tier_by_id, active_tier_ids, migrate_legacy_tier,
    get_roster_group_scheme, set_roster_group_scheme,
    get_selected_group_category_id, set_selected_group_category_id,
    get_group_label, set_group_label, set_group_labels,
    compute_group_display, default_group_label,
)

# --- private I/O helpers (needed by sibling sub-modules and test monkeypatches) ---
from . import _io

# Re-export public constants from _io so consumers can still access config.SERVICE etc.
DEFAULT_OPENROUTER_MODEL = _io.DEFAULT_OPENROUTER_MODEL
OPENROUTER_MODEL_PRESETS = _io.OPENROUTER_MODEL_PRESETS
OPENROUTER_PRESET_SCENARIO_INPUT_TOKENS = _io.OPENROUTER_PRESET_SCENARIO_INPUT_TOKENS
OPENROUTER_PRESET_SCENARIO_OUTPUT_TOKENS = _io.OPENROUTER_PRESET_SCENARIO_OUTPUT_TOKENS
CANVAS_BASE_DEFAULT = _io.CANVAS_BASE_DEFAULT
DOWNLOAD_ROOT_DEFAULT = _io.DOWNLOAD_ROOT_DEFAULT
CONFIG_PATH = _io.CONFIG_PATH
SYNCED_KEYS = _io.SYNCED_KEYS
SERVICE = _io.SERVICE
TOKEN_KEY = _io.TOKEN_KEY
OPENROUTER_KEY = _io.OPENROUTER_KEY