"""Feedback tools result parsing, validation, and re-identification helpers."""
import csv
import io
import json
import re

from api.feedback_vault import Vault
from api.feedback_contract import CONTRACT_VERSION
from api.powergrader import writing_timeline

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


def _top_level_json_blocks(text: str):
    """Yield (start, end, value) for each decodable JSON value in `text`, left
    to right. A value's own nested arrays/objects are not reported again as
    separate blocks, since their span is already consumed by the outer one.
    """
    decoder = json.JSONDecoder()
    consumed_to = 0
    for match in re.finditer(r"[\[{]", text):
        start = match.start()
        if start < consumed_to:
            continue
        try:
            value, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        yield start, end, value
        consumed_to = end


def _first_json_block(text: str):
    """Return the JSON results embedded in prose or one or more code fences.

    A model reply is not always one clean JSON value: it may lead with a
    sentence of prose that itself decodes as a small JSON object, or wrap
    each student in its own fenced object instead of one shared array.
    Collect every top-level decodable value instead of stopping at whichever
    comes first, then choose:

    - if any value is a list, the widest one wins (ties broken by the later
      one), since a wrapping array is almost certainly the real results and
      a short leading note must not shadow it;
    - otherwise, if two or more values look like a single result (each
      carries a `pseudonym`), treat the reply as one fenced object per
      student and combine them into a list;
    - otherwise, fall back to the widest decodable value, on the theory that
      the biggest block is more likely to be substance than an aside.
    """
    blocks = list(_top_level_json_blocks(text))
    if not blocks:
        raise ValueError("the model reply did not contain valid JSON results")

    def widest(candidates):
        return max(candidates, key=lambda block: (block[1] - block[0], block[0]))

    lists_found = [block for block in blocks if isinstance(block[2], list)]
    if lists_found:
        return widest(lists_found)[2]

    dicts_found = [block[2] for block in blocks if isinstance(block[2], dict)]
    result_like = [d for d in dicts_found if isinstance(d.get("pseudonym"), str) and d.get("pseudonym")]
    if len(result_like) > 1:
        return result_like
    if result_like:
        return result_like[0]

    return widest(blocks)[2]


def _unwrap_dict_results(data: dict) -> list:
    """Pull a results list out of a wrapper object.

    `results` is the documented key, but models substitute close synonyms
    (`scores`, `students`, ...). Accept any single list-valued key; when more
    than one qualifies, prefer whichever one's first element looks like a
    result object rather than guessing. A bare object with no wrapper at
    all, carrying its own `pseudonym`, is one result rather than none.
    """
    results = data.get("results")
    if isinstance(results, list):
        return results

    list_valued = [v for v in data.values() if isinstance(v, list)]
    if len(list_valued) == 1:
        return list_valued[0]
    if len(list_valued) > 1:
        for value in list_valued:
            first = value[0] if value else None
            if isinstance(first, dict) and first.get("pseudonym"):
                return value
        return []  # several lists, none look like results: don't guess

    if isinstance(data.get("pseudonym"), str) and data.get("pseudonym"):
        return [data]
    return []


def parse_results(text: str) -> list:
    """Parse the LLM's result JSON: an array, an object wrapping the results
    under `results` (or a close synonym), or a single bare result object.

    Models routinely wrap the JSON in a markdown code fence, lead with a
    sentence of prose, or reshape the wrapper entirely; tolerate all of that
    rather than quietly returning zero results for the batch.
    """
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("the model reply was empty")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = _first_json_block(raw)
    if isinstance(data, dict):
        data = _unwrap_dict_results(data)
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
        if "writing_process_observations" in r and not isinstance(
            r.get("writing_process_observations"), str
        ):
            errors.append(f"{where}: 'writing_process_observations' must be text")
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
        writing_observation = r.get("writing_process_observations", "")
        if not isinstance(writing_observation, str):
            writing_observation = ""
        # The contract forbids integrity conclusions here; enforce it rather than
        # trusting the prompt.  This is the single funnel where model results
        # become teacher-facing rows, so the guard belongs here.
        writing_observation = writing_timeline.sanitize_process_observation(writing_observation)
        out.append({
            "resolved":  who is not None,
            "real_name": (who or {}).get("real_name", ""),
            "canvas_id": (who or {}).get("canvas_id", ""),
            "sis_id":    (who or {}).get("sis_id", ""),
            "item_id":   r.get("item_id", ""),
            "score":     r.get("score"),
            "feedback":  normalize_ai_feedback(r.get("feedback", ""), disclosure),
            "disclosure": disclosure,
            "writing_process_observations": writing_observation,
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
            "writing_process_observations": "\n\n".join(
                str(item.get("writing_process_observations") or "").strip()
                for item in items
                if str(item.get("writing_process_observations") or "").strip()
            ),
        }
    return merged


def item_rows_by_uid(rows: list) -> dict[str, list[dict]]:
    """Keep validated AI drafts item-local for New Quiz review.

    ``merge_rows_by_uid`` remains the compatibility summary used by ordinary
    PowerGrader feedback.  This companion deliberately keeps the same
    reidentified/validated rows rather than introducing another scoring shape.
    """
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        if not row.get("resolved") or not row.get("item_id"):
            continue
        grouped.setdefault(str(row.get("canvas_id") or ""), []).append({
            "item_id": str(row.get("item_id")),
            "score": row.get("score"),
            "feedback": row.get("feedback") or "",
        })
    return grouped


def reidentified_csv(rows: list) -> str:
    """Render re-identified results as CSV text (for the ToEnter folder)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Student", "Canvas ID", "SIS ID", "Item", "Score", "Feedback", "Disclosure"])
    for r in rows:
        w.writerow([r["real_name"], r["canvas_id"], r["sis_id"], r["item_id"],
                    "" if r["score"] is None else r["score"], r["feedback"], r["disclosure"]])
    return buf.getvalue()
