"""QuizForge-API configuration.

Canvas base URL and the token remain machine-local. Synced user content moves to
the OneDrive workspace when it exists. One-time migration copies the synced keys
into workspace/settings.json and leaves the old machine keys in place as dead
data so the two-PC last-writer-wins sync model stays simple.
"""
import json
import os

import keyring

from . import workspace

SERVICE   = "quizforge-api"
TOKEN_KEY = "canvas_token"
OPENROUTER_KEY = "openrouter_key"

# Default LLM for FeedbackExpert via OpenRouter. Editable in the UI — verify the
# exact model id at openrouter.ai/models; OpenRouter slugs change over time.
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-sonnet-4.5"

# Empty by default — the first-run wizard collects the teacher's Canvas URL.
# An empty base is the signal that onboarding is not yet complete.
CANVAS_BASE_DEFAULT   = ""
DOWNLOAD_ROOT_DEFAULT = os.path.join(os.path.expanduser("~"), "Desktop", "Canvas Downloads")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
SYNCED_KEYS = ("saved_courses", "extra_time", "late_sweep", "calendars", "tier_tags",
               "ai_ta_persona", "roster_student_settings", "roster_tier_schemes",
               "roster_group_schemes")


def _source_label(key: str) -> str:
    """Prettify a calendar key into a display label (district-agnostic)."""
    return key.replace("_", " ").title().replace("Isd", "ISD")


def _machine_load():
    if not os.path.exists(CONFIG_PATH):
        return {"canvas_base": CANVAS_BASE_DEFAULT, "saved_courses": []}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("canvas_base", CANVAS_BASE_DEFAULT)
    data.setdefault("saved_courses", [])
    # One-time migration: flat academic_calendar → calendars dict
    if "academic_calendar" in data and "calendars" not in data:
        old = data.pop("academic_calendar", {})
        src = old.get("source") or "custom"
        data["calendars"] = {}
        if old.get("no_count_dates") or old.get("grading_periods"):
            data["calendars"][src] = {
                "label":          _source_label(src),
                "no_count_dates": sorted(set(old.get("no_count_dates") or [])),
                "grading_periods": old.get("grading_periods") or [],
            }
        _machine_save(data)
    return data


def _machine_save(state):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _workspace_settings_path() -> str | None:
    root = workspace.workspace_root()
    if not root:
        return None
    return os.path.join(root, "settings.json")


def _workspace_load():
    path = _workspace_settings_path()
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _workspace_save(state):
    path = _workspace_settings_path()
    if not path:
        return
    # OneDrive sync is last-writer-wins here; conflict copies like settings-<PC>.json
    # are ignored by the app and left for the user to reconcile manually.
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _synced_state():
    machine = _machine_load()
    path = _workspace_settings_path()
    if not path:
        return machine
    if not os.path.exists(path):
        _workspace_save({k: machine[k] for k in SYNCED_KEYS if k in machine})
    ws = _workspace_load()
    merged = dict(machine)
    merged.update(ws)
    return merged


def _save_synced_key(key, value):
    path = _workspace_settings_path()
    if not path:
        state = _machine_load()
        state[key] = value
        _machine_save(state)
        return
    ws = _workspace_load()
    ws[key] = value
    _workspace_save(ws)


# --------------------------------------------------------------------------
# Canvas account (base URL + token)
# --------------------------------------------------------------------------

def get_canvas_base() -> str:
    return _machine_load()["canvas_base"]


def set_canvas_base(base_url: str):
    state = _machine_load()
    state["canvas_base"] = base_url.rstrip("/")
    _machine_save(state)


def get_token() -> str | None:
    return keyring.get_password(SERVICE, TOKEN_KEY)


def set_token(token: str):
    keyring.set_password(SERVICE, TOKEN_KEY, token)


def token_is_set() -> bool:
    t = get_token()
    return bool(t and not t.startswith("PASTE"))


def get_download_root() -> str:
    state = _machine_load()
    if state.get("download_root"):
        return state["download_root"]
    root = workspace.workspace_root()
    if root:
        return os.path.join(root, "Exports")
    return DOWNLOAD_ROOT_DEFAULT


def set_download_root(path: str):
    state = _machine_load()
    state["download_root"] = path
    _machine_save(state)


def save_canvas_account(base_url: str, token: str | None = None):
    """Save base URL (always) and token (only if provided)."""
    set_canvas_base(base_url)
    if token:
        set_token(token)


# --------------------------------------------------------------------------
# OpenRouter (FeedbackExpert LLM) — key in keyring, model machine-local
# --------------------------------------------------------------------------

def get_openrouter_key() -> str | None:
    return keyring.get_password(SERVICE, OPENROUTER_KEY)


def set_openrouter_key(key: str):
    keyring.set_password(SERVICE, OPENROUTER_KEY, key)


def has_openrouter_key() -> bool:
    k = get_openrouter_key()
    return bool(k and not k.startswith("PASTE"))


def get_openrouter_model() -> str:
    return _machine_load().get("openrouter_model") or DEFAULT_OPENROUTER_MODEL


def set_openrouter_model(model: str):
    state = _machine_load()
    state["openrouter_model"] = (model or "").strip()
    _machine_save(state)


# --------------------------------------------------------------------------
# Workspace path (machine-local override)
# --------------------------------------------------------------------------

def get_workspace_path() -> str | None:
    return _machine_load().get("workspace_path") or None


def set_workspace_path(path: str):
    state = _machine_load()
    state["workspace_path"] = path.strip()
    _machine_save(state)


# --------------------------------------------------------------------------
# Bookmarked courses
# --------------------------------------------------------------------------

def saved_courses() -> list[dict]:
    """All bookmarked courses [{id, name, nickname, active}].
    `active` defaults to True for older entries that pre-date the field.
    """
    courses = _synced_state().get("saved_courses", [])
    for c in courses:
        c.setdefault("active", True)
    return courses


def active_courses() -> list[dict]:
    """Only the active bookmarked courses — used for dashboard dropdowns."""
    return [c for c in saved_courses() if c.get("active", True)]


def set_course_active(course_id: str, active: bool):
    """Mark a bookmarked course active or inactive."""
    state = _synced_state()
    for c in state.get("saved_courses", []):
        if c["id"] == str(course_id):
            c["active"] = active
            break
    _save_synced_key("saved_courses", state.get("saved_courses", []))


def bookmark_course(course_id: str, course_name: str, nickname: str = ""):
    state = _synced_state()
    course_id = str(course_id)
    courses = state.setdefault("saved_courses", [])
    for c in courses:
        if c["id"] == course_id:
            c["name"] = course_name
            c["nickname"] = nickname or course_name
            _save_synced_key("saved_courses", courses)
            return
    courses.append({
        "id":       course_id,
        "name":     course_name,
        "nickname": nickname or course_name,
        "active":   True,
    })
    _save_synced_key("saved_courses", courses)


def remove_course(course_id: str):
    state = _synced_state()
    state["saved_courses"] = [c for c in state.get("saved_courses", [])
                               if c["id"] != str(course_id)]
    _save_synced_key("saved_courses", state.get("saved_courses", []))


# --------------------------------------------------------------------------
# Gradebook Expert — extra-time roster + late-sweep settings
# --------------------------------------------------------------------------

SWEEP_DEFAULTS = {
    "skip_weekends":    True,
    "holidays":         [],  # ["YYYY-MM-DD", ...] — school holidays / no-count days
    "honor_extra_time": True,
}


def get_extra_time(course_id: str) -> list[dict]:
    """Students with standing extra time in a course: [{id, name, days}]."""
    return _synced_state().get("extra_time", {}).get(str(course_id), [])


def set_extra_time(course_id: str, students: list[dict]):
    state = _synced_state()
    state.setdefault("extra_time", {})[str(course_id)] = students
    _save_synced_key("extra_time", state.get("extra_time", {}))


TIER_NAMES = ["Support", "Core", "Accelerate", "Extend"]


def get_tier_tags() -> dict:
    """Per-teacher map of tier readiness name -> neutral student-visible display tag.
    Missing/blank means 'no tag' (clean assignment name). Synced across machines."""
    saved = _synced_state().get("tier_tags", {})
    return {name: str(saved.get(name, "")).strip() for name in TIER_NAMES}


def set_tier_tags(tags: dict):
    clean = {name: str(tags.get(name, "")).strip() for name in TIER_NAMES}
    _save_synced_key("tier_tags", clean)


# --------------------------------------------------------------------------
# FeedbackExpert — AI-TA persona library (synced, multiple starters)
# --------------------------------------------------------------------------

AI_TA_PERSONA_DEFAULT = {"name": "", "personality": ""}

# Three shipped starter personas — Sage (default), Pip, Coach Vale
BUILTIN_PERSONAS = [
    {
        "id": "sage",
        "name": "Sage",
        "personality": (
            "A calm, thoughtful mentor. Warm and patient; names what's working "
            "before what to fix; precise without being cold."
        ),
    },
    {
        "id": "pip",
        "name": "Pip",
        "personality": (
            "Upbeat and energetic; plain language, short punchy sentences. "
            "Built for reluctant readers — high warmth, low jargon."
        ),
    },
    {
        "id": "coach_vale",
        "name": "Coach Vale",
        "personality": (
            "Direct and action-oriented; frames feedback as 'your next rep.' "
            "Concrete, motivating, no fluff."
        ),
    },
]


def list_personas() -> list[dict]:
    """Return built-in + any custom personas the teacher has saved.
    Each: {id, name, personality, builtin: bool}."""
    builtins = [{"builtin": True, **p} for p in BUILTIN_PERSONAS]
    custom_raw = _synced_state().get("custom_personas", [])
    custom = [{"id": c.get("id", ""), "name": c.get("name", ""),
               "personality": c.get("personality", ""), "builtin": False}
              for c in custom_raw if c.get("name")]
    return builtins + custom


def get_persona(persona_id: str = "") -> dict:
    """Get a persona by id, falling back to 'sage' or blank default."""
    for p in list_personas():
        if p["id"] == (persona_id or "sage"):
            return {"name": p["name"], "personality": p["personality"]}
    return dict(AI_TA_PERSONA_DEFAULT)


def save_custom_persona(persona_id: str, name: str, personality: str):
    """Add or update a custom persona. Builtins are read-only."""
    if any(p["id"] == persona_id for p in BUILTIN_PERSONAS):
        return  # can't overwrite builtins
    state = _synced_state()
    custom = state.setdefault("custom_personas", [])
    for i, p in enumerate(custom):
        if p.get("id") == persona_id:
            custom[i] = {"id": persona_id, "name": name.strip(), "personality": personality.strip()}
            _save_synced_key("custom_personas", custom)
            return
    custom.append({"id": persona_id, "name": name.strip(), "personality": personality.strip()})
    _save_synced_key("custom_personas", custom)


def remove_custom_persona(persona_id: str):
    """Remove a user-created persona."""
    if any(p["id"] == persona_id for p in BUILTIN_PERSONAS):
        return
    state = _synced_state()
    state["custom_personas"] = [p for p in state.get("custom_personas", [])
                                 if p.get("id") != persona_id]
    _save_synced_key("custom_personas", state["custom_personas"])


# Legacy single-persona getter/setter — kept for backward compat, delegates to library.
def get_ai_ta_persona() -> dict:
    saved = _synced_state().get("ai_ta_persona", {})
    return {"name": str(saved.get("name", "")).strip(),
            "personality": str(saved.get("personality", "")).strip()}


def set_ai_ta_persona(name: str, personality: str = ""):
    _save_synced_key("ai_ta_persona",
                     {"name": (name or "").strip(), "personality": (personality or "").strip()})


# --------------------------------------------------------------------------
# FeedbackExpert — Feedback Patterns (synced)
# --------------------------------------------------------------------------

FEEDBACK_PATTERNS_DEFAULT = [
    {
        "id": "basic",
        "name": "Glows & Grows (Basic)",
        "score_from_rubric": True,
        "glows": {"min": 2, "max": 3},
        "grows": {"min": 1, "max": 2},
        "strategy_sentences": {"min": 2, "max": 3},
        "sign_with_persona": True,
    },
]


def list_feedback_patterns() -> list[dict]:
    return list(_synced_state().get("feedback_patterns", FEEDBACK_PATTERNS_DEFAULT))


def set_feedback_patterns(patterns: list[dict]):
    _save_synced_key("feedback_patterns", patterns)


def get_sweep_settings() -> dict:
    saved = _synced_state().get("late_sweep", {})
    return {**SWEEP_DEFAULTS, **saved}


def set_sweep_settings(settings: dict):
    state = _synced_state()
    state["late_sweep"] = {k: settings[k] for k in SWEEP_DEFAULTS if k in settings}
    _save_synced_key("late_sweep", state.get("late_sweep", {}))


# --------------------------------------------------------------------------
# Academic calendars — district no-count dates for sweep / extensions
# Multiple named calendars can be active simultaneously.
# --------------------------------------------------------------------------

def get_calendars() -> dict:
    """Return {key: {label, no_count_dates, grading_periods}} for all stored calendars."""
    return dict(_synced_state().get("calendars", {}))


def set_calendar(key: str, label: str, dates: list,
                 periods: list | None = None) -> None:
    state = _synced_state()
    state.setdefault("calendars", {})[key] = {
        "label":          label,
        "no_count_dates": sorted(set(dates)),
        "grading_periods": periods or [],
    }
    _save_synced_key("calendars", state.get("calendars", {}))


def remove_calendar(key: str) -> None:
    state = _synced_state()
    state.setdefault("calendars", {}).pop(key, None)
    _save_synced_key("calendars", state.get("calendars", {}))


def clear_all_calendars() -> None:
    state = _synced_state()
    state["calendars"] = {}
    _save_synced_key("calendars", state.get("calendars", {}))


def get_combined_calendar_for_range(
        date_from: str | None = None,
        date_to:   str | None = None) -> dict:
    """Merge all stored calendars, filtered to dates within [date_from, date_to].
    Grading periods are included if they overlap the range.
    Returns {no_count_dates, grading_periods}."""
    no_count: set = set()
    periods:  list = []
    for cal in _synced_state().get("calendars", {}).values():
        for d in cal.get("no_count_dates", []):
            if date_from and d < date_from: continue
            if date_to   and d > date_to:   continue
            no_count.add(d)
        for gp in cal.get("grading_periods", []):
            if date_from and gp["end"]   < date_from: continue
            if date_to   and gp["start"] > date_to:   continue
            periods.append(gp)
    return {
        "no_count_dates": sorted(no_count),
        "grading_periods": sorted(periods, key=lambda p: p["start"]),
    }


# --------------------------------------------------------------------------
# FeedbackExpert — Protected-names store + literary character packs
# Not PII — fine to sync and to ship the packs in-repo.
# --------------------------------------------------------------------------

LITERARY_PACKS = [
    {"id": "outsiders",  "title": "The Outsiders",
     "names": ["Ponyboy","Johnny","Dally","Dallas","Sodapop","Darry","Two-Bit","Cherry","Bob"]},
    {"id": "hunger_games","title": "The Hunger Games",
     "names": ["Katniss","Peeta","Gale","Prim","Haymitch","Effie","Rue","Cinna","Snow"]},
    {"id": "giver",       "title": "The Giver",
     "names": ["Jonas","Asher","Fiona","Gabriel","Lily"]},
    {"id": "romeo_juliet","title": "Romeo & Juliet",
     "names": ["Romeo","Juliet","Tybalt","Mercutio","Benvolio","Capulet","Montague","Friar"]},
]


def list_protected_packs() -> list[dict]:
    """Return all literary packs with their enabled status."""
    enabled = _synced_state().get("protected_packs_enabled", {})
    return [
        {"id": p["id"], "title": p["title"], "names": p["names"],
         "enabled": enabled.get(p["id"], False)}
        for p in LITERARY_PACKS
    ]


def set_pack_enabled(pack_id: str, enabled: bool):
    state = _synced_state()
    enabled_map = state.get("protected_packs_enabled", {})
    enabled_map[pack_id] = enabled
    _save_synced_key("protected_packs_enabled", enabled_map)


def get_custom_protected_names() -> list[str]:
    return list(_synced_state().get("protected_names_custom", []))


def set_custom_protected_names(names: list[str]):
    clean = sorted(set(n.strip() for n in names if n and n.strip()))
    _save_synced_key("protected_names_custom", clean)


def active_protected_names() -> set[str]:
    """Union of enabled packs' names + custom, lowercased."""
    result: set[str] = set()
    for p in list_protected_packs():
        if p["enabled"]:
            result.update(n.lower() for n in p["names"])
    for n in get_custom_protected_names():
        result.add(n.lower())
    return result


# --------------------------------------------------------------------------
# Runtime credential bundle
# --------------------------------------------------------------------------

def resolve_env(course_id: str) -> dict:
    """CANVAS_BASE / COURSE_ID / CANVAS_TOKEN dict for subprocess env."""
    token = get_token()
    if not token:
        raise ValueError("No Canvas token saved — go to Settings and paste your token.")
    return {
        "CANVAS_BASE": get_canvas_base(),
        "COURSE_ID":   str(course_id),
        "CANVAS_TOKEN": token,
    }


# --------------------------------------------------------------------------
# Routines — machine-local automation state (NOT synced; see SPEC_Routines)
# --------------------------------------------------------------------------

def get_routine_states() -> dict:
    """{routine_id: {enabled, every_hours, params, last_run, last_summary}}"""
    return _machine_load().get("routines", {})


def set_routine_state(routine_id: str, patch: dict):
    state = _machine_load()
    routines = state.setdefault("routines", {})
    cur = routines.setdefault(routine_id, {})
    cur.update(patch)
    _machine_save(state)


# --------------------------------------------------------------------------
# Student Reports — synced-workspace output root + machine-local monitored cohort
# --------------------------------------------------------------------------

STUDENT_REPORTS_DEFAULT = os.path.join(
    os.path.expanduser("~"), "Desktop", "Canvas Student Reports")


def get_student_reports_root() -> str:
    """Synced-workspace folder (OneDrive — in-tenant/FERPA-safe, reachable at meetings).
    Mirrors get_download_root(): under the workspace if configured, else local fallback."""
    state = _machine_load()
    if state.get("student_reports_root"):
        return state["student_reports_root"]
    root = workspace.workspace_root()
    if root:
        return os.path.join(root, "Student Reports")
    return STUDENT_REPORTS_DEFAULT


def set_student_reports_root(path: str):
    state = _machine_load()
    state["student_reports_root"] = path
    _machine_save(state)


def get_monitored_students() -> dict:
    """{user_id(str): {name, note}} — machine-local; note is private, never in a packet."""
    return _machine_load().get("monitored_students", {})


def set_monitored_student(user_id: str, name: str, note: str = ""):
    state = _machine_load()
    mon = state.setdefault("monitored_students", {})
    mon[str(user_id)] = {"name": name, "note": note}
    _machine_save(state)


def remove_monitored_student(user_id: str):
    state = _machine_load()
    mon = state.setdefault("monitored_students", {})
    mon.pop(str(user_id), None)
    _machine_save(state)


# --------------------------------------------------------------------------
# Roster Console — local student settings (tier, planned group)
# Stored per course in the synced workspace. Contains Canvas user ids — treat
# as private synced data like extra_time.
# --------------------------------------------------------------------------


def get_roster_student_settings(course_id: str) -> dict:
    """{user_id: {tier, planned_group}} for a course."""
    return _synced_state().get("roster_student_settings", {}).get(str(course_id), {})


def set_roster_student_settings(course_id: str, settings: dict):
    """Replace local roster settings for one course."""
    state = _synced_state()
    all_settings = state.setdefault("roster_student_settings", {})
    all_settings[str(course_id)] = settings
    _save_synced_key("roster_student_settings", all_settings)


def update_roster_student_settings(course_id: str, user_id: str, patch: dict):
    """Patch one student's local roster settings."""
    state = _synced_state()
    all_settings = state.setdefault("roster_student_settings", {})
    course_settings = all_settings.setdefault(str(course_id), {})
    student = course_settings.setdefault(str(user_id), {})
    for k, v in patch.items():
        if v is None:
            student.pop(k, None)
        else:
            student[k] = v
    _save_synced_key("roster_student_settings", all_settings)


# --------------------------------------------------------------------------
# Roster Console V2 — tier scheme (alias system, per-course)
# --------------------------------------------------------------------------

ROSTER_DEFAULT_TIER_SCHEME = [
    {
        "id": "support",
        "teacher_label": "Support",
        "meaning": "below-level",
        "alias": "Blue",
        "order": 10,
        "active": True,
    },
    {
        "id": "core",
        "teacher_label": "Core",
        "meaning": "on-level",
        "alias": "Red",
        "order": 20,
        "active": True,
    },
    {
        "id": "extend",
        "teacher_label": "Extend",
        "meaning": "advanced",
        "alias": "White",
        "order": 30,
        "active": True,
    },
]


def _validate_tier_scheme(scheme: list[dict]) -> str | None:
    """Validate a tier scheme. Returns error string or None if valid."""
    if not isinstance(scheme, list) or not scheme:
        return "Scheme must be a non-empty list."
    seen_ids: set[str] = set()
    for i, t in enumerate(scheme):
        if not isinstance(t, dict):
            return f"Item {i} is not an object."
        tid = t.get("id", "")
        if not tid or not isinstance(tid, str):
            return f"Item {i}: missing or invalid 'id'."
        if tid in seen_ids:
            return f"Duplicate tier id '{tid}'."
        seen_ids.add(tid)
        label = t.get("teacher_label", "")
        if not label or not isinstance(label, str):
            return f"Tier '{tid}': missing 'teacher_label'."
        alias = t.get("alias", "")
        if not alias or not isinstance(alias, str):
            return f"Tier '{tid}': missing or blank 'alias'."
    return None


def _normalize_tier_scheme(scheme: list[dict]) -> list[dict]:
    """Ensure every tier has order, active, and clean defaults."""
    out = []
    for i, t in enumerate(scheme):
        out.append({
            "id": str(t.get("id", "")),
            "teacher_label": str(t.get("teacher_label", "")),
            "meaning": str(t.get("meaning", "")),
            "alias": str(t.get("alias", "")),
            "order": t.get("order", (i + 1) * 10),
            "active": t.get("active", True),
        })
    return out


def get_roster_tier_scheme(course_id: str) -> list[dict]:
    """Return this course's tier scheme, or the default three-tier scheme."""
    schemes = _synced_state().get("roster_tier_schemes", {})
    saved = schemes.get(str(course_id))
    if saved:
        return _normalize_tier_scheme(saved)
    return list(ROSTER_DEFAULT_TIER_SCHEME)


def set_roster_tier_scheme(course_id: str, scheme: list[dict]):
    """Validate and save this course's tier scheme."""
    err = _validate_tier_scheme(scheme)
    if err:
        raise ValueError(err)
    norm = _normalize_tier_scheme(scheme)
    state = _synced_state()
    schemes = state.setdefault("roster_tier_schemes", {})
    schemes[str(course_id)] = norm
    _save_synced_key("roster_tier_schemes", schemes)


def roster_tier_by_id(course_id: str) -> dict:
    """Return {tier_id: tier_dict} for all saved tiers (active + inactive)."""
    scheme = get_roster_tier_scheme(course_id)
    return {t["id"]: t for t in scheme}


def active_tier_ids(course_id: str) -> set[str]:
    """Return set of active tier ids for a course."""
    return {t["id"] for t in get_roster_tier_scheme(course_id) if t.get("active", True)}


def migrate_legacy_tier(course_id: str, user_id: str, tier_val: str, roster_settings: dict | None = None) -> str | None:
    """Migrate a legacy V1 'tier' string to a V2 'tier_id'.

    If the tier matches a known teacher_label (case-insensitive), return the
    matching tier id. If unknown, add it to the course scheme as a custom tier
    and return its slug. Returns None if tier_val is blank.
    """
    if not tier_val:
        return None
    scheme = get_roster_tier_scheme(course_id)
    tier_lower = tier_val.strip().lower()
    for t in scheme:
        if t.get("teacher_label", "").lower() == tier_lower:
            return t["id"]
    # Unknown tier — add to scheme as custom entry
    import re
    slug = re.sub(r'[^a-z0-9]+', '_', tier_lower).strip('_') or f"tier_{len(scheme)}"
    new_tier = {
        "id": slug,
        "teacher_label": tier_val.strip(),
        "meaning": "",
        "alias": tier_val.strip(),
        "order": 1000,
        "active": True,
    }
    scheme.append(new_tier)
    set_roster_tier_scheme(course_id, scheme)
    return slug


# --------------------------------------------------------------------------
# Roster Console V3 — Canvas group-backed group schemes (per-course)
# --------------------------------------------------------------------------

# Default color-to-label mapping for common Canvas group names
DEFAULT_GROUP_LABELS = {
    "blue": "Support",
    "red": "Core",
    "white": "Extend",
}


def get_roster_group_scheme(course_id: str) -> dict:
    """Return the group scheme for a course.

    Returns: {
        "selected_group_category_id": "<category_id>" | None,
        "group_labels": {
            "<group_id>": {"teacher_label": "Support", "meaning": "..."}
        }
    }
    """
    schemes = _synced_state().get("roster_group_schemes", {})
    return schemes.get(str(course_id), {})


def set_roster_group_scheme(course_id: str, scheme: dict):
    """Save the group scheme for a course."""
    state = _synced_state()
    schemes = state.setdefault("roster_group_schemes", {})
    schemes[str(course_id)] = scheme
    _save_synced_key("roster_group_schemes", schemes)


def get_selected_group_category_id(course_id: str) -> str | None:
    """Get the preferred group category ID for a course."""
    scheme = get_roster_group_scheme(course_id)
    return scheme.get("selected_group_category_id")


def set_selected_group_category_id(course_id: str, category_id: str | None):
    """Save the preferred group category ID for a course."""
    scheme = get_roster_group_scheme(course_id)
    scheme["selected_group_category_id"] = category_id
    set_roster_group_scheme(course_id, scheme)


def get_group_label(course_id: str, group_id: str) -> dict | None:
    """Get the teacher label and meaning for a Canvas group."""
    scheme = get_roster_group_scheme(course_id)
    return scheme.get("group_labels", {}).get(str(group_id))


def set_group_label(course_id: str, group_id: str, teacher_label: str, meaning: str = ""):
    """Save a teacher label for a Canvas group."""
    scheme = get_roster_group_scheme(course_id)
    labels = scheme.setdefault("group_labels", {})
    labels[str(group_id)] = {
        "teacher_label": teacher_label,
        "meaning": meaning,
    }
    set_roster_group_scheme(course_id, scheme)


def set_group_labels(course_id: str, labels: dict):
    """Save multiple group labels for a course."""
    scheme = get_roster_group_scheme(course_id)
    scheme["group_labels"] = labels
    set_roster_group_scheme(course_id, scheme)


def compute_group_display(teacher_label: str | None, group_name: str) -> str:
    """Compute display text: 'Support / Blue' or just 'Blue'."""
    if teacher_label and teacher_label != group_name:
        return f"{teacher_label} / {group_name}"
    return group_name


def default_group_label(group_name: str) -> str | None:
    """Return default label for common group names (Blue -> Support, etc.)."""
    return DEFAULT_GROUP_LABELS.get(group_name.lower())
