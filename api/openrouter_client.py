"""Minimal OpenRouter client for FeedbackExpert scoring.

Split into pure builders/parsers (offline-testable) and one thin live call. The
caller MUST run feedback_safety.scan_payload() and confirm GREEN before invoking
score() — this module assumes it is handed an already-pseudonymized bundle.
"""
import json

try:
    from feedback_pipeline import build_contract_text, parse_results
except ModuleNotFoundError:
    from api.feedback_pipeline import build_contract_text, parse_results

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


def estimate_tokens(bundle: dict, rubric_text: str = "") -> int:
    """Rough input-token estimate (~4 chars/token) for a cost heads-up."""
    chars = len(json.dumps(bundle)) + len(rubric_text or "")
    return max(1, chars // 4)


def build_request(bundle: dict, rubric_text: str, persona: dict, model: str) -> dict:
    """Build the chat-completions request body (pure)."""
    name = (persona or {}).get("name") or "your AI teaching assistant"
    personality = (persona or {}).get("personality") or ""
    system = build_contract_text(name)
    if personality:
        system += f"\n\nYour personality/tone: {personality}\n"
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
          model: str, http_post=None, timeout: int = 120) -> list:
    """Live call. `http_post` is injectable for tests. Returns parsed results list."""
    if not api_key:
        raise ValueError("No OpenRouter API key set.")
    if http_post is None:
        import requests
        http_post = requests.post
    body = build_request(bundle, rubric_text, persona, model)
    r = http_post(ENDPOINT, headers={"Authorization": f"Bearer {api_key}",
                                     "Content-Type": "application/json"},
                  json=body, timeout=timeout)
    r.raise_for_status()
    return parse_response(r.json())
