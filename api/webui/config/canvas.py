"""Canvas account, OpenRouter, and workspace path configuration.

Machine-local config (base URL, token, OpenRouter key, model, workspace path).
Uses lazy module-reference so monkeypatches to config._io propagate correctly.
"""
from . import _io as _io_code

import keyring
import os
from .. import workspace


# --------------------------------------------------------------------------
# Canvas account (base URL + token)
# --------------------------------------------------------------------------

def get_canvas_base() -> str:
    return _io_code._machine_load()["canvas_base"]


def set_canvas_base(base_url: str):
    _io_code._modify_machine(
        lambda state: state.__setitem__("canvas_base", base_url.rstrip("/")) or state
    )


def get_token() -> str | None:
    return keyring.get_password(_io_code.SERVICE, _io_code.TOKEN_KEY)


def set_token(token: str):
    keyring.set_password(_io_code.SERVICE, _io_code.TOKEN_KEY, token)


def token_is_set() -> bool:
    t = get_token()
    return bool(t and not t.startswith("PASTE"))


def get_download_root() -> str:
    state = _io_code._machine_load()
    if state.get("download_root"):
        return state["download_root"]
    root = workspace.workspace_root()
    if root:
        return os.path.join(root, "Exports")
    return _io_code.DOWNLOAD_ROOT_DEFAULT


def set_download_root(path: str):
    _io_code._modify_machine(
        lambda state: state.__setitem__("download_root", path) or state
    )


def save_canvas_account(base_url: str, token: str | None = None):
    """Save base URL (always) and token (only if provided)."""
    set_canvas_base(base_url)
    if token:
        set_token(token)


# --------------------------------------------------------------------------
# OpenRouter (feedback tools LLM) — key in keyring, model machine-local
# --------------------------------------------------------------------------

def get_openrouter_key() -> str | None:
    return keyring.get_password(_io_code.SERVICE, _io_code.OPENROUTER_KEY)


def set_openrouter_key(key: str):
    keyring.set_password(_io_code.SERVICE, _io_code.OPENROUTER_KEY, key)


def has_openrouter_key() -> bool:
    k = get_openrouter_key()
    return bool(k and not k.startswith("PASTE"))


def get_openrouter_model() -> str:
    model = (_io_code._machine_load().get("openrouter_model") or "").strip()
    if not model or model == "openrouter/auto":
        return _io_code.DEFAULT_OPENROUTER_MODEL
    return model


def set_openrouter_model(model: str):
    _io_code._modify_machine(
        lambda state: state.__setitem__("openrouter_model", (model or "").strip()) or state
    )


def openrouter_model_presets() -> list[dict]:
    presets = []
    for p in _io_code.OPENROUTER_MODEL_PRESETS:
        item = dict(p)
        inp = item.get("input_per_mtok")
        out = item.get("output_per_mtok")
        if inp is not None and out is not None:
            item["scenario_cost"] = (
                inp * _io_code.OPENROUTER_PRESET_SCENARIO_INPUT_TOKENS
                + out * _io_code.OPENROUTER_PRESET_SCENARIO_OUTPUT_TOKENS
            ) / 1_000_000
        item.setdefault("cost_tier", _openrouter_cost_tier(item.get("scenario_cost")))
        presets.append(item)
    return presets


def _openrouter_cost_tier(scenario_cost) -> str:
    try:
        cost = float(scenario_cost)
    except (TypeError, ValueError):
        return "$?"
    if cost < 0.10:
        return "$"
    if cost < 0.50:
        return "$$"
    return "$$$"


# --------------------------------------------------------------------------
# Workspace path (machine-local override)
# --------------------------------------------------------------------------

def get_workspace_path() -> str | None:
    return _io_code._machine_load().get("workspace_path") or None


def set_workspace_path(path: str):
    _io_code._modify_machine(
        lambda state: state.__setitem__("workspace_path", path.strip()) or state
    )


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
