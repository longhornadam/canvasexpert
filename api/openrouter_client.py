"""Minimal OpenRouter client for feedback tools scoring.

Split into pure builders/parsers (offline-testable) and one thin live call. The
caller MUST run feedback_safety.scan_payload() and confirm GREEN before invoking
score() — this module assumes it is handed an already-pseudonymized bundle.
"""
import json
from json import JSONDecodeError

try:
    from feedback_pipeline import build_contract_text, parse_results, persona_signoff
except ModuleNotFoundError:
    from api.feedback_pipeline import build_contract_text, parse_results, persona_signoff

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MODELS_ENDPOINT = "https://openrouter.ai/api/v1/models"

DEFAULT_OUTPUT_TOKENS_PER_STUDENT = 500
_KNOWN_PREMIUM_MODEL_MARKERS = (
    "gpt-5.5",
    "gpt-5.5-pro",
    "gpt-4.5",
    "gpt-4-turbo",
    "opus",
    "o1-pro",
)


class OpenRouterResponseError(ValueError):
    """Raised when OpenRouter returns a response PowerGrader cannot parse."""

    def __init__(
        self,
        message: str,
        *,
        context: str = "",
        status_code: str = "unknown",
        response_snippet: str = "",
    ):
        super().__init__(message)
        self.context = context
        self.status_code = status_code
        self.response_snippet = response_snippet


def _response_text(resp) -> str:
    try:
        return (resp.text or "").strip()
    except Exception:
        return ""


def _status_code(resp) -> str:
    try:
        return str(resp.status_code)
    except Exception:
        return "unknown"


def _json_or_raise(resp, *, context: str) -> dict:
    try:
        return resp.json()
    except (JSONDecodeError, ValueError) as e:
        text = _response_text(resp)
        snippet = text[:500] if text else "<empty response body>"
        status = _status_code(resp)
        raise OpenRouterResponseError(
            f"{context} returned non-JSON response "
            f"(HTTP {status}): {snippet}",
            context=context,
            status_code=status,
            response_snippet=snippet,
        ) from e


def _raise_for_status_or_raise(resp, *, context: str) -> None:
    try:
        resp.raise_for_status()
    except Exception as e:
        text = _response_text(resp)
        snippet = text[:500] if text else "<empty response body>"
        status = _status_code(resp)
        raise OpenRouterResponseError(
            f"{context} returned HTTP {status}: {snippet}",
            context=context,
            status_code=status,
            response_snippet=snippet,
        ) from e


def estimate_tokens(bundle: dict, rubric_text: str = "") -> int:
    """Rough input-token estimate (~4 chars/token) for a cost heads-up."""
    chars = len(json.dumps(bundle)) + len(rubric_text or "")
    return max(1, chars // 4)


def estimate_request_input_tokens(
    bundle: dict,
    rubric_text: str = "",
    persona: dict = None,
    feedback_pattern: dict = None,
) -> int:
    """Rough full request estimate, including system instructions/persona."""
    body = build_request(
        bundle or {},
        rubric_text or "",
        persona or {},
        "__estimate__",
        feedback_pattern,
    )
    chars = len(json.dumps(body.get("messages") or [], ensure_ascii=False))
    return max(1, chars // 4)


def _price_per_mtok(value) -> float | None:
    try:
        return float(value) * 1_000_000
    except (TypeError, ValueError):
        return None


def estimate_feedback_output_tokens(student_count: int, per_student: int = None) -> int:
    """Conservative output estimate for rubric score + Glows/Grows feedback."""
    per = int(per_student or DEFAULT_OUTPUT_TOKENS_PER_STUDENT)
    return max(per, max(0, int(student_count or 0)) * per)


def model_pricing(model: str, *, http_get=None, timeout: int = 15) -> dict | None:
    """Fetch OpenRouter list pricing for an exact model id.

    OpenRouter's pricing values are cost per token; this returns dollars per
    million tokens so UI/routes can show teacher-readable prices.
    """
    model = (model or "").strip()
    if not model or model == "openrouter/auto":
        return None
    if http_get is None:
        import requests
        http_get = requests.get
    r = http_get(MODELS_ENDPOINT, timeout=timeout)
    _raise_for_status_or_raise(r, context="OpenRouter model list")
    for row in (_json_or_raise(r, context="OpenRouter model list").get("data") or []):
        if str(row.get("id") or "").strip() != model:
            continue
        pricing = row.get("pricing") or {}
        input_per = _price_per_mtok(pricing.get("prompt"))
        output_per = _price_per_mtok(pricing.get("completion"))
        if input_per is None or output_per is None:
            return None
        return {
            "model": model,
            "input_per_mtok": input_per,
            "output_per_mtok": output_per,
        }
    return None


def estimate_cost_usd(input_tokens: int, output_tokens: int, pricing: dict | None) -> float | None:
    if not pricing:
        return None
    try:
        return (
            pricing["input_per_mtok"] * int(input_tokens or 0)
            + pricing["output_per_mtok"] * int(output_tokens or 0)
        ) / 1_000_000
    except (KeyError, TypeError, ValueError):
        return None


def teacher_workflow_budget(
    bundle: dict,
    rubric_text: str,
    model: str,
    *,
    student_count: int = None,
    persona: dict = None,
    feedback_pattern: dict = None,
    output_tokens_per_student: int = None,
    http_get=None,
) -> dict:
    """Return price visibility before a paid scoring call.

    Exact models with verified live pricing are allowed, even when expensive.
    Auto Router and unverified model IDs stay blocked because the app cannot show
    the teacher a reliable estimate before money is spent.
    """
    model = (model or "").strip()
    students = student_count
    if students is None:
        students = len((bundle or {}).get("students") or [])
    input_tokens = estimate_request_input_tokens(
        bundle, rubric_text, persona=persona, feedback_pattern=feedback_pattern
    )
    output_tokens = estimate_feedback_output_tokens(
        students, per_student=output_tokens_per_student
    )
    price = None
    price_error = ""
    try:
        price = model_pricing(model, http_get=http_get)
    except Exception as e:
        price_error = str(e)

    estimate = estimate_cost_usd(input_tokens, output_tokens, price)
    premium_marker = any(marker in model.lower() for marker in _KNOWN_PREMIUM_MODEL_MARKERS)
    ok = True
    reasons: list[str] = []
    warnings: list[str] = []

    if model == "openrouter/auto":
        ok = False
        reasons.append("OpenRouter Auto Router is disabled for teacher auto-scoring because its price can vary by route.")
    if price:
        if premium_marker or price["output_per_mtok"] >= 10 or price["input_per_mtok"] >= 3:
            warnings.append("premium-priced model; review the estimate before class-scale scoring")
    elif premium_marker:
        ok = False
        reasons.append("selected model looks like a premium model, and live pricing could not be verified")
    else:
        ok = False
        reasons.append("live pricing could not be verified for the selected model")

    return {
        "ok": ok,
        "model": model,
        "input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "pricing": price,
        "estimated_cost": estimate,
        "price_error": price_error,
        "reasons": reasons,
        "warnings": warnings,
    }


def build_request(bundle: dict, rubric_text: str, persona: dict, model: str,
                  feedback_pattern: dict | None = None) -> dict:
    """Build the chat-completions request body (pure)."""
    name = (persona or {}).get("name") or "your teaching assistant"
    personality = (persona or {}).get("personality") or ""
    system = build_contract_text(name, persona=persona)
    if personality:
        system += f"\n\nYour personality/tone: {personality}\n"

    # Inject feedback pattern instructions
    if feedback_pattern:
        pattern = feedback_pattern
        gl = pattern.get("glows", {"min": 2, "max": 3})
        gr = pattern.get("grows", {"min": 1, "max": 2})
        ss = pattern.get("strategy_sentences", {"min": 2, "max": 3})
        system += (
            f"\n\n--- FEEDBACK PATTERN: {pattern.get('name', 'Glows & Grows (Basic)')} ---\n"
            f"For EACH response, structure your 'feedback' field as:\n"
            f"- Score derived from the rubric ({'use rubric scoring' if pattern.get('score_from_rubric', True) else 'use your best judgment'})\n"
            f"- {gl.get('min', 2)}–{gl.get('max', 3)} Glows (what the student did well)\n"
            f"- {gr.get('min', 1)}–{gr.get('max', 2)} Grows (areas to improve)\n"
            f"- A {ss.get('min', 2)}–{ss.get('max', 3)} sentence overall improvement strategy\n"
        )
        if pattern.get("sign_with_persona", True):
            signoff = persona_signoff(persona, name)
            if not signoff:
                signoff = ""
        else:
            signoff = ""
        if signoff:
            system += (
                f"\nEnd each feedback entry with exactly this persona signoff once: "
                f"'{signoff}' "
                f"Do not add a separate signature or disclosure."
            )

    if rubric_text:
        system += f"\n\n--- RUBRIC (score strictly by this) ---\n{rubric_text}\n"
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",
             "content": "Score every response in this bundle and return ONLY the "
                        "JSON array described above:\n\n" + json.dumps(bundle, ensure_ascii=False)},
        ],
        "temperature": 0.2,
    }


def parse_response(resp_json: dict) -> list:
    """Extract the results array from an OpenRouter chat-completions response (pure)."""
    content = (((resp_json or {}).get("choices") or [{}])[0]
               .get("message", {}).get("content", "")) or ""
    return parse_results(content)


def score(bundle: dict, rubric_text: str, persona: dict, *, api_key: str,
          model: str, http_post=None, timeout: int = 120,
          feedback_pattern: dict | None = None) -> list:
    """Live call. `http_post` is injectable for tests. Returns parsed results list."""
    if not api_key:
        raise ValueError("No OpenRouter API key set.")
    if http_post is None:
        import requests
        http_post = requests.post
    body = build_request(bundle, rubric_text, persona, model, feedback_pattern)
    r = http_post(ENDPOINT, headers={"Authorization": f"Bearer {api_key}",
                                     "Content-Type": "application/json"},
                  json=body, timeout=timeout)
    _raise_for_status_or_raise(r, context="OpenRouter scoring")
    return parse_response(_json_or_raise(r, context="OpenRouter scoring"))
