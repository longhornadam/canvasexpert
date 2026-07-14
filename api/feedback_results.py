"""Feedback tools result parsing, validation, and re-identification helpers."""
import csv
import io
import json
import re

try:                                   # script context (run from api/)
    from feedback_vault import Vault
except ModuleNotFoundError:            # package context (tests: api.feedback_results)
    from api.feedback_vault import Vault

try:
    from feedback_contract import CONTRACT_VERSION
except ModuleNotFoundError:
    from api.feedback_contract import CONTRACT_VERSION

_SECTION_LABELS = (
    r"Score|Glows?|Grows?|Next(?:\s+step| steps?)?|Strategy|Overall|"
    r"Evidence|Try this|Revision target|Why this score"
)
_AI_SIGNATURE_LINE_RE = re.compile(
    r"(?im)^\s*(?:[-\u2013\u2014]\s*)?[\w .,'&-]{1,100}\s+"
    r"\((?:AI|AI teaching assistant)\)\.?\s*$"
)
_DISCLOSURE_NAME_RE = re.compile(
    r"Drafted by\s+(.+?)\s+\(AI\),\s*reviewed by your teacher\.?",
    re.IGNORECASE,
)


def _format_feedback_linebreaks(text: str) -> str:
    """Make model feedback readable as plain text in a Canvas comment box."""
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+(?=(" + _SECTION_LABELS + r")\s*:)", "\n\n",
                  text, flags=re.IGNORECASE)
    text = re.sub(
        r"\s+(?=Drafted by [^.\n]+?\(AI\), reviewed by your teacher\.?)",
        "\n\n", text, flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+(?=[-*]\s+(?:Glow|Grow|Next|Evidence|Try)\b)", "\n",
                  text, flags=re.IGNORECASE)
    text = "\n".join(line.strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _remove_phrase(text: str, phrase: str) -> str:
    phrase = (phrase or "").strip()
    if not phrase:
        return text
    pattern = re.escape(phrase).replace(r"\ ", r"\s+")
    return re.sub(pattern, "", text, flags=re.IGNORECASE).strip()


def _remove_persona_signature(text: str, disclosure: str) -> str:
    match = _DISCLOSURE_NAME_RE.search(disclosure or "")
    if not match:
        return _AI_SIGNATURE_LINE_RE.sub("", text)
    persona = re.escape(match.group(1).strip())
    pattern = (
        rf"(?i)(?:[-\u2013\u2014]\s*)?{persona}\s+"
        rf"\((?:AI|AI teaching assistant)\)\.?"
    )
    return re.sub(pattern, "", text).strip()


def normalize_ai_feedback(feedback: str, disclosure: str = "") -> str:
    """Clean AI feedback before it becomes a teacher-facing Canvas comment.

    Some personas carry a separate disclosure/signoff field, while some model
    outputs also sign the feedback inline. When a disclosure is present, prefer one
    copy in the final comment. When it is absent, leave the formatted feedback
    unsigned.
    """
    text = _format_feedback_linebreaks(feedback)
    disclosure = _format_feedback_linebreaks(disclosure)
    if not disclosure:
        return _AI_SIGNATURE_LINE_RE.sub("", text).strip()

    text = _remove_phrase(text, disclosure)
    text = _AI_SIGNATURE_LINE_RE.sub("", text)
    text = _remove_persona_signature(text, disclosure)
    text = _format_feedback_linebreaks(text)
    return f"{text}\n\n{disclosure}".strip() if text else disclosure


def _first_json_block(text: str):
    """Return the first JSON array/object embedded in prose or a code fence."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\[{]", text):
        try:
            data, _ = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        return data
    raise ValueError("the model reply did not contain valid JSON results")


def parse_results(text: str) -> list:
    """Parse the LLM's result JSON (an array, or an object wrapping `results`).

    Models routinely wrap the JSON in a markdown code fence or lead with a
    sentence of prose; tolerate that instead of failing the scoring batch.
    """
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("the model reply was empty")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = _first_json_block(raw)
    if isinstance(data, dict):
        data = data.get("results", [])
    return data if isinstance(data, list) else []


def validate_results(results, bundle: dict = None, vault: Vault = None,
                     *, contract_version: str = CONTRACT_VERSION) -> dict:
    """Validate scoring output against the Feedback Scoring Contract (v1).

    See docs/contracts/feedback-scoring-contract.md. Accepts either the wrapped
    object ({contract_version, results:[...]}) or a bare array. `bundle` and
    `vault` are optional cross-checks: with them we confirm every result maps to
    a real (pseudonym, item_id) the LLM was actually given and that scores fit the
    item's max. Returns {ok, errors:[...], warnings:[...], n:int}. `ok` is False
    only on hard errors — out-of-range scores / uncovered students are warnings,
    since the teacher reviews before any push.
    """
    errors, warnings = [], []

    if isinstance(results, dict):
        ver = str(results.get("contract_version", "") or "")
        if ver and ver.split(".")[0] != str(contract_version).split(".")[0]:
            warnings.append(f"contract_version {ver} != expected {contract_version}")
        results = results.get("results", [])
    if not isinstance(results, list):
        return {"ok": False, "errors": ["top-level results is not a list/array"],
                "warnings": [], "n": 0}

    expected, possible = set(), {}
    if bundle:
        for s in bundle.get("students", []):
            for r in s.get("responses", []):
                key = (s.get("pseudonym"), str(r.get("item_id", "")))
                expected.add(key)
                possible[key] = r.get("possible")

    seen = set()
    for i, r in enumerate(results):
        where = f"results[{i}]"
        if not isinstance(r, dict):
            errors.append(f"{where}: not an object")
            continue
        ps, it = r.get("pseudonym"), str(r.get("item_id", ""))
        if not ps or not isinstance(ps, str):
            errors.append(f"{where}: missing/invalid 'pseudonym'")
        if not it:
            errors.append(f"{where}: missing 'item_id'")
        fb = r.get("feedback")
        if not isinstance(fb, str) or not fb.strip():
            errors.append(f"{where}: 'feedback' must be non-empty text")
        sc = r.get("score", None)
        if sc is not None and not isinstance(sc, (int, float)):
            errors.append(f"{where}: 'score' must be a number or null")
        key = (ps, it)
        if key in seen:
            errors.append(f"{where}: duplicate result for {key}")
        seen.add(key)
        if vault is not None and ps and vault.reverse(ps) is None:
            errors.append(f"{where}: pseudonym '{ps}' is not in the vault")
        if bundle:
            if key not in expected:
                errors.append(f"{where}: {key} was not in the bundle the LLM scored")
            else:
                pmax = possible.get(key)
                if isinstance(sc, (int, float)) and isinstance(pmax, (int, float)) \
                        and not (0 <= sc <= pmax):
                    warnings.append(f"{where}: score {sc} is outside 0..{pmax}")

    if bundle:
        for key in sorted(expected - seen):
            warnings.append(f"no result for {key} (student left unscored)")

    return {"ok": not errors, "errors": errors, "warnings": warnings, "n": len(results)}


def reidentify(results: list, vault: Vault) -> list:
    """Map pseudonymous results back to real students via the vault. Unknown
    pseudonyms are marked `resolved: False` rather than dropped."""
    out = []
    for r in results:
        who = vault.reverse(r.get("pseudonym", ""))
        disclosure = r.get("disclosure", "")
        out.append({
            "resolved":  who is not None,
            "real_name": (who or {}).get("real_name", ""),
            "canvas_id": (who or {}).get("canvas_id", ""),
            "sis_id":    (who or {}).get("sis_id", ""),
            "item_id":   r.get("item_id", ""),
            "score":     r.get("score"),
            "feedback":  normalize_ai_feedback(r.get("feedback", ""), disclosure),
            "disclosure": disclosure,
        })
    return out


def merge_rows_by_uid(rows: list) -> dict:
    """Combine per-item reidentified rows into one draft per student.

    Multi-item work (a New Quiz with an essay item and an upload item, for
    example) produces one result per (pseudonym, item_id), but a PowerGrader
    session holds one AI draft per student. Item drafts must be merged —
    a plain ``{canvas_id: row}`` dict silently keeps only the last item.
    Returns ``{canvas_id: row}`` with unresolved rows excluded.
    """
    grouped: dict[str, list] = {}
    for row in rows:
        if not row.get("resolved"):
            continue
        grouped.setdefault(str(row.get("canvas_id") or ""), []).append(row)

    merged: dict[str, dict] = {}
    for uid, items in grouped.items():
        if len(items) == 1:
            merged[uid] = items[0]
            continue
        disclosure = next((i.get("disclosure") for i in items if i.get("disclosure")), "")
        sections = []
        for index, item in enumerate(items, 1):
            text = _remove_phrase(str(item.get("feedback") or ""), disclosure)
            score = item.get("score")
            label = "not AI-scored" if score is None else f"AI score {score}"
            sections.append(f"Item {index} of {len(items)} ({label}):\n{text}".strip())
        feedback = "\n\n".join(sections)
        if disclosure:
            feedback = f"{feedback}\n\n{disclosure}".strip()
        scores = [item.get("score") for item in items]
        total = (
            sum(scores)
            if scores and all(isinstance(s, (int, float)) for s in scores)
            else None
        )
        merged[uid] = {
            **items[0],
            "item_id": ",".join(str(item.get("item_id") or "") for item in items),
            "score": total,
            "feedback": feedback,
        }
    return merged


def reidentified_csv(rows: list) -> str:
    """Render re-identified results as CSV text (for the ToEnter folder)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Student", "Canvas ID", "SIS ID", "Item", "Score", "Feedback", "Disclosure"])
    for r in rows:
        w.writerow([r["real_name"], r["canvas_id"], r["sis_id"], r["item_id"],
                    "" if r["score"] is None else r["score"], r["feedback"], r["disclosure"]])
    return buf.getvalue()
