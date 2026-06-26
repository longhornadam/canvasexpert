"""Settings routes for Canvas Expert.

One APIRouter; all 6 POST settings routes (Canvas account, course bookmarks,
download root, connection test). All are thin pass-throughs to config.*.

Routes: POST /settings/canvas
        POST /settings/openrouter
        POST /settings/courses/bookmark
        POST /settings/courses/{course_id}/remove
        POST /settings/courses/{course_id}/set-active
        POST /settings/download-root
        POST /settings/test-connection
"""
import requests

from fastapi import APIRouter, Form, Query
from fastapi.responses import JSONResponse

from .. import config

router = APIRouter(tags=["settings"])

SCENARIO_INPUT_TOKENS = 50_000
SCENARIO_OUTPUT_TOKENS = 10_000


def _probe_openrouter_key(api_key: str | None) -> dict:
    if not api_key:
        return {"valid": False, "error": "No OpenRouter API key saved."}
    try:
        r = requests.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
    except requests.RequestException as e:
        return {"valid": False, "error": str(e)}
    if r.status_code != 200:
        try:
            msg = (r.json().get("error") or {}).get("message") or r.text[:200]
        except ValueError:
            msg = r.text[:200]
        return {"valid": False, "error": f"HTTP {r.status_code}: {msg}"}
    data = r.json().get("data") or r.json()
    return {
        "valid": True,
        "label": data.get("label") or data.get("name") or "",
        "usage": data.get("usage"),
        "limit": data.get("limit"),
    }


def _price_per_mtok(value) -> float | None:
    try:
        return float(value) * 1_000_000
    except (TypeError, ValueError):
        return None


def _model_row(model: dict) -> dict:
    pricing = model.get("pricing") or {}
    prompt = _price_per_mtok(pricing.get("prompt"))
    completion = _price_per_mtok(pricing.get("completion"))
    return {
        "id": str(model.get("id") or "").strip(),
        "name": str(model.get("name") or model.get("id") or "").strip(),
        "context_length": model.get("context_length"),
        "created": model.get("created") or 0,
        "input_per_mtok": prompt,
        "output_per_mtok": completion,
        "scenario_cost": (
            None if prompt is None or completion is None
            else (prompt * SCENARIO_INPUT_TOKENS + completion * SCENARIO_OUTPUT_TOKENS) / 1_000_000
        ),
    }


def _pick_latest(rows: list[dict], predicate, prefer_latest: str = "") -> dict | None:
    matches = [r for r in rows if predicate(r)]
    if not matches:
        return None
    if prefer_latest:
        latest_matches = [r for r in matches if prefer_latest in r["id"].lower()]
        if latest_matches:
            return sorted(latest_matches, key=lambda r: r.get("created") or 0, reverse=True)[0]
    return sorted(matches, key=lambda r: r.get("created") or 0, reverse=True)[0]


def _current_major_models(rows: list[dict]) -> list[dict]:
    def text_model(r: dict) -> bool:
        hay = (r["id"] + " " + r["name"]).lower()
        return not any(x in hay for x in ("image", "audio", "vision", "banana"))

    specs = [
        ("Anthropic Opus", lambda r: text_model(r) and "anthropic/" in r["id"] and "opus" in r["id"], "opus-latest", "latest alias"),
        ("Anthropic Sonnet", lambda r: text_model(r) and "anthropic/" in r["id"] and "sonnet" in r["id"], "sonnet-latest", "latest alias"),
        ("OpenAI GPT", lambda r: text_model(r) and "openai/gpt-" in r["id"] and "codex" not in r["id"], "", "newest listed"),
        ("Google Gemini Pro", lambda r: text_model(r) and "google/" in r["id"] and "gemini" in r["id"] and "pro" in r["id"], "gemini-pro-latest", "latest alias"),
        ("Google Gemini Flash", lambda r: text_model(r) and "google/" in r["id"] and "gemini" in r["id"] and "flash" in r["id"], "gemini-flash-latest", "latest alias"),
        ("Moonshot Kimi", lambda r: text_model(r) and "moonshotai/" in r["id"] and "kimi" in r["id"], "kimi-latest", "latest alias"),
        ("DeepSeek", lambda r: text_model(r) and "deepseek/" in r["id"] and "distill" not in r["id"], "", "newest listed"),
        ("Qwen", lambda r: text_model(r) and "qwen/" in r["id"], "", "newest listed"),
        ("Meta Llama", lambda r: text_model(r) and "meta-llama/" in r["id"] and "guard" not in r["id"] and ":free" not in r["id"], "", "newest listed"),
    ]
    picked = []
    seen = set()
    for family, predicate, prefer, strategy in specs:
        row = _pick_latest(rows, predicate, prefer)
        if not row or row["id"] in seen:
            continue
        item = dict(row)
        item["family"] = family
        item["strategy"] = strategy if not prefer or prefer in row["id"].lower() else "newest listed"
        picked.append(item)
        seen.add(row["id"])
    priced = [r for r in picked if r.get("scenario_cost") is not None]
    if priced:
        low = min(r["scenario_cost"] for r in priced)
        high = max(r["scenario_cost"] for r in priced)
        picked.insert(0, {
            "id": "openrouter/auto",
            "name": "OpenRouter Auto Router",
            "family": "Auto Router",
            "strategy": "routes dynamically",
            "input_per_mtok": None,
            "output_per_mtok": None,
            "scenario_cost": None,
            "scenario_cost_low": low,
            "scenario_cost_high": high,
        })
    return picked


@router.post("/settings/canvas")
def save_canvas_account(base_url: str = Form(...), token: str = Form("")):
    config.save_canvas_account(base_url, token or None)
    return JSONResponse({"ok": True})


@router.post("/settings/openrouter")
def save_openrouter(api_key: str = Form(""), model: str = Form("")):
    if api_key.strip():
        config.set_openrouter_key(api_key.strip())
    if model.strip():
        config.set_openrouter_model(model.strip())
    probe = _probe_openrouter_key(config.get_openrouter_key())
    return JSONResponse({
        "ok": True,
        "has_key": config.has_openrouter_key(),
        "key_valid": probe["valid"],
        "key_error": probe.get("error", ""),
        "key_label": probe.get("label", ""),
        "model": config.get_openrouter_model(),
    })


@router.post("/settings/openrouter/test")
def test_openrouter(api_key: str = Form("")):
    probe = _probe_openrouter_key(api_key.strip() or config.get_openrouter_key())
    return JSONResponse({"ok": probe["valid"], **probe})


@router.get("/settings/openrouter/models")
def openrouter_models(q: str = Query("", max_length=80), limit: int = Query(120, ge=1, le=300)):
    try:
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=15)
        r.raise_for_status()
        models = r.json().get("data") or []
    except requests.RequestException as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)

    needle = q.strip().lower()
    rows = []
    for m in models:
        row = _model_row(m)
        if not row["id"]:
            continue
        if needle and needle not in row["id"].lower() and needle not in row["name"].lower():
            continue
        rows.append(row)
        if len(rows) >= limit:
            break
    return JSONResponse({
        "ok": True,
        "models": rows,
        "majors": _current_major_models([_model_row(m) for m in models]),
        "scenario": {
            "label": "30 1000-word essays + rubric + feedback template",
            "input_tokens": SCENARIO_INPUT_TOKENS,
            "output_tokens": SCENARIO_OUTPUT_TOKENS,
        },
    })


@router.post("/settings/courses/bookmark")
def bookmark_course(course_id: str = Form(...), course_name: str = Form(...),
                    nickname: str = Form("")):
    config.bookmark_course(course_id, course_name, nickname)
    return JSONResponse({"ok": True})


@router.post("/settings/courses/{course_id}/remove")
def remove_course(course_id: str):
    config.remove_course(course_id)
    return JSONResponse({"ok": True})


@router.post("/settings/courses/{course_id}/set-active")
def set_course_active(course_id: str, active: str = Form(...)):
    config.set_course_active(course_id, active.lower() in ("true", "1", "yes"))
    return JSONResponse({"ok": True})


@router.post("/settings/download-root")
def save_download_root(path: str = Form(...)):
    config.set_download_root(path.strip())
    return JSONResponse({"ok": True})


@router.post("/settings/test-connection")
def test_connection(base_url: str = Form(...), token: str = Form("")):
    """Read-only probe — verifies token+base before saving.

    When `token` is omitted (empty string), falls back to the token already
    stored in the OS keychain. This lets the teacher hit "Test connection"
    without re-entering the token they saved previously.
    """
    base = base_url.rstrip("/")
    effective_token = token or config.get_token()
    if not effective_token:
        return JSONResponse({"ok": False,
                             "error": "No token provided and none saved yet. Paste a token first."})
    try:
        r = requests.get(f"{base}/api/v1/users/self",
                         headers={"Authorization": f"Bearer {effective_token}"},
                         timeout=15)
    except requests.RequestException as e:
        return JSONResponse({"ok": False, "error": str(e)})
    if r.status_code != 200:
        return JSONResponse({"ok": False,
                             "error": f"HTTP {r.status_code}: {r.text[:300]}"})
    d = r.json()
    return JSONResponse({"ok": True,
                         "display_name": d.get("name", d.get("short_name", "Unknown"))})
