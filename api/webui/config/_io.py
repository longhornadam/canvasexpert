"""Private I/O helpers for the config package.

Exports the machine-local and workspace-synced persistence primitives.
Every other config/* module imports from here.
"""
import json
import os

import keyring

from .. import workspace

SERVICE   = "quizforge-api"
TOKEN_KEY = "canvas_token"
OPENROUTER_KEY = "openrouter_key"

# Cost-conscious OpenRouter default for teacher grading. Do not use
# openrouter/auto here: the router can select premium models with very high
# output prices, which is unsafe for routine class-scale scoring.
DEFAULT_OPENROUTER_MODEL = "deepseek/deepseek-v4-pro"

OPENROUTER_MODEL_PRESETS = [
    {
        "id": DEFAULT_OPENROUTER_MODEL,
        "label": "DeepSeek V4 Pro",
        "note": "Default for PowerGrader; low cost, large context",
        "input_per_mtok": 0.435,
        "output_per_mtok": 0.87,
        "cost_tier": "$",
    },
    {
        "id": "deepseek/deepseek-v4-flash",
        "label": "DeepSeek V4 Flash",
        "note": "Fastest low-cost DeepSeek option",
        "input_per_mtok": 0.09,
        "output_per_mtok": 0.18,
        "cost_tier": "$",
    },
    {
        "id": "~google/gemini-flash-latest",
        "label": "Gemini Flash Latest",
        "note": "Latest Flash alias",
        "input_per_mtok": 1.50,
        "output_per_mtok": 9.00,
        "cost_tier": "$$",
    },
    {
        "id": "~openai/gpt-mini-latest",
        "label": "OpenAI GPT Mini Latest",
        "note": "Latest mini alias",
        "input_per_mtok": 0.75,
        "output_per_mtok": 4.50,
        "cost_tier": "$",
    },
    {
        "id": "~moonshotai/kimi-latest",
        "label": "Kimi Latest",
        "note": "Latest Kimi alias",
        "input_per_mtok": 0.66,
        "output_per_mtok": 3.41,
        "cost_tier": "$",
    },
    {
        "id": "~anthropic/claude-haiku-latest",
        "label": "Claude Haiku Latest",
        "note": "Latest Haiku alias",
        "input_per_mtok": 1.00,
        "output_per_mtok": 5.00,
        "cost_tier": "$",
    },
    {
        "id": "~google/gemini-pro-latest",
        "label": "Gemini Pro Latest",
        "note": "Latest Pro alias; review estimate before class-scale scoring",
        "input_per_mtok": 2.00,
        "output_per_mtok": 12.00,
        "cost_tier": "$$",
    },
    {
        "id": "~anthropic/claude-sonnet-latest",
        "label": "Claude Sonnet Latest",
        "note": "Latest Sonnet alias; premium option",
        "input_per_mtok": 3.00,
        "output_per_mtok": 15.00,
        "cost_tier": "$$",
    },
    {
        "id": "~anthropic/claude-opus-latest",
        "label": "Claude Opus Latest",
        "note": "Latest Opus alias; premium option",
        "input_per_mtok": 5.00,
        "output_per_mtok": 25.00,
        "cost_tier": "$$$",
    },
    {
        "id": "~openai/gpt-latest",
        "label": "OpenAI GPT Latest",
        "note": "Latest GPT alias; premium option",
        "input_per_mtok": 5.00,
        "output_per_mtok": 30.00,
        "cost_tier": "$$$",
    },
    {
        "id": "openai/gpt-chat-latest",
        "label": "OpenAI GPT Chat Latest",
        "note": "Latest ChatGPT alias; premium option",
        "input_per_mtok": 5.00,
        "output_per_mtok": 30.00,
        "cost_tier": "$$$",
    },
]

OPENROUTER_PRESET_SCENARIO_INPUT_TOKENS = 50_000
OPENROUTER_PRESET_SCENARIO_OUTPUT_TOKENS = 10_000

# Empty by default — the first-run wizard collects the teacher's Canvas URL.
# An empty base is the signal that onboarding is not yet complete.
CANVAS_BASE_DEFAULT   = ""
DOWNLOAD_ROOT_DEFAULT = os.path.join(os.path.expanduser("~"), "Desktop", "Canvas Downloads")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")
SYNCED_KEYS = ("saved_courses", "extra_time", "late_sweep", "calendars", "tier_tags",
               "ai_ta_persona", "roster_student_settings", "roster_tier_schemes",
               "roster_group_schemes", "monitored_students")


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
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        # OSError [Errno 22] on Windows = OneDrive cloud-only file not yet downloaded
        return {}


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
    # Backfill synced keys that exist machine-local but were never written to the
    # workspace — covers keys promoted to SYNCED_KEYS after the workspace was first
    # seeded (e.g. monitored_students, now PII-synced). Machine data only fills gaps;
    # the workspace copy stays authoritative once present.
    missing = {k: machine[k] for k in SYNCED_KEYS if k in machine and k not in ws}
    if missing:
        ws.update(missing)
        _workspace_save(ws)
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