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

# Empty by default — the first-run wizard collects the teacher's Canvas URL.
# An empty base is the signal that onboarding is not yet complete.
CANVAS_BASE_DEFAULT   = ""
DOWNLOAD_ROOT_DEFAULT = os.path.join(os.path.expanduser("~"), "Desktop", "Canvas Downloads")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
SYNCED_KEYS = ("saved_courses", "extra_time", "late_sweep", "calendars", "tier_tags",
               "ai_ta_persona")


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
# FeedbackExpert — AI-TA persona (name + personality). Disclosed in feedback.
# --------------------------------------------------------------------------

AI_TA_PERSONA_DEFAULT = {"name": "", "personality": ""}


def get_ai_ta_persona() -> dict:
    saved = _synced_state().get("ai_ta_persona", {})
    return {"name": str(saved.get("name", "")).strip(),
            "personality": str(saved.get("personality", "")).strip()}


def set_ai_ta_persona(name: str, personality: str = ""):
    _save_synced_key("ai_ta_persona",
                     {"name": (name or "").strip(), "personality": (personality or "").strip()})


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
