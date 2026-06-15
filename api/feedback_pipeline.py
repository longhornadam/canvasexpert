"""FeedbackExpert pipeline: pseudonymize student work, emit an LLM-ready scoring
bundle, and re-identify the LLM's results back to real students via the vault.

Pure-ish stdlib + the NQ parser. Offline-testable. Only pseudonymized payloads are
ever written to the ForLLM folder; real identities live only in the vault.
"""
import csv
import io
import json
import os

try:                                   # script context (run from api/)
    from nq_report import constructed_responses, html_to_text, parse_student_analysis_file
    from feedback_vault import Vault
except ModuleNotFoundError:            # package context (tests: api.feedback_pipeline)
    from api.nq_report import constructed_responses, html_to_text, parse_student_analysis_file
    from api.feedback_vault import Vault

CONTRACT_VERSION = "1.0"
_REVIEW_NOTE = ("Pseudonymized for privacy. Review the response text for any "
                "self-identifying details (names, places) before sending to an LLM.")


def _safe(name, max_len=80):
    import re
    s = re.sub(r'[^\w\- ]+', "", (name or "").strip())
    return (re.sub(r'\s+', " ", s)[:max_len] or "quiz").strip()


# --------------------------------------------------------------------------
# Pseudonymize -> bundle
# --------------------------------------------------------------------------

def pseudonymize(parsed: dict, vault: Vault, quiz_title: str) -> dict:
    """Build an LLM-safe bundle: one entry per student (by pseudonym) with their
    constructed (written) responses only — no names, ids, or sections. Mutates the
    vault (assigns pseudonyms); caller saves the vault."""
    students = []
    for s in parsed.get("students", []):
        written = constructed_responses(s)
        if not written:
            continue
        pseudo = vault.get_or_assign(s.get("canvas_id"), s.get("name", ""), s.get("sis_id", ""))
        students.append({
            "pseudonym": pseudo,
            "responses": [{
                "item_id":  it.get("item_id"),
                "prompt":   it.get("prompt", ""),
                "response": html_to_text(it.get("response", "")),
                "possible": it.get("points_possible_est"),
            } for it in written],
        })
    return {"contract_version": CONTRACT_VERSION, "quiz_title": quiz_title,
            "review_required": True, "note": _REVIEW_NOTE, "students": students}


def pseudonymize_submissions(submissions: list, vault: Vault,
                              assignment_title: str) -> dict:
    """Build an LLM-safe bundle from Canvas API submissions (assignments path).

    Each submission is keyed on the vault by canvas_id (student user_id). One entry
    per student with the assignment as a single response item. Mutates the vault;
    caller saves.

    Args:
        submissions: list of Canvas submission objects from /students/submissions
        vault: Vault instance
        assignment_title: display name for the assignment
    """
    # Group submissions by student (latest per assignment). The real name/sis come
    # from include[]=user on the fetch; they go ONLY into the vault, never the bundle.
    by_student: dict = {}
    for s in submissions:
        uid = str(s.get("user_id", ""))
        if not uid:
            continue
        a = s.get("assignment") or {}
        user = s.get("user") or {}
        prompt = html_to_text(a.get("description") or "")
        response = html_to_text(s.get("body") or "")
        if not response and not (s.get("attachments") or []):
            continue
        entry = {
            "item_id":  str(a.get("id", "")),
            "prompt":   prompt,
            "response": response,
            "possible": a.get("points_possible"),
            "submitted_at": s.get("submitted_at", ""),
            "score":    s.get("score"),
            "real_name": user.get("name") or user.get("sortable_name") or "",
            "sis_id":    str(user.get("sis_user_id") or ""),
        }
        # Keep latest submission per assignment
        existing = by_student.get(uid)
        if existing is None or (entry["submitted_at"] or "") > (existing.get("_submitted_at") or ""):
            by_student[uid] = {**entry, "_submitted_at": entry["submitted_at"]}

    students = []
    for uid, entry in by_student.items():
        pseudo = vault.get_or_assign(uid, entry["real_name"], entry["sis_id"])
        students.append({
            "pseudonym": pseudo,
            "responses": [{
                "item_id":  entry["item_id"],
                "prompt":   entry["prompt"],
                "response": entry["response"],
                "possible": entry["possible"],
            }],
        })

    return {"contract_version": CONTRACT_VERSION,
            "quiz_title": assignment_title,
            "source": "assignment",
            "review_required": True, "note": _REVIEW_NOTE, "students": students}


def build_contract_text(ai_ta_name: str = "your AI teaching assistant") -> str:
    """Instructions the teacher pastes into their LLM alongside the bundle + rubric.
    Extends the Essay Scorer skill: keyed batch output for automatic re-identification,
    with mandatory disclosure naming the AI-TA."""
    return f"""You are {ai_ta_name}, an AI teaching assistant helping a real teacher
score student writing and draft feedback. A RubricForge rubric is attached as
Knowledge — score strictly by it, do not invent criteria.

You will receive a JSON bundle of pseudonymized responses. For EACH response return
one result object. Output ONLY a JSON array, each element exactly:

  {{"pseudonym": "<copy>", "item_id": "<copy>", "score": <number>,
    "feedback": "<actionable, kind, rubric-anchored feedback for the student>",
    "disclosure": "Drafted by {ai_ta_name} (AI), reviewed by your teacher."}}

Rules:
- Copy `pseudonym` and `item_id` back EXACTLY so results can be matched.
- Quote briefly from the response to justify the score.
- Every `feedback` value must end with the `disclosure` sentence — students are
  told, honestly, that an AI helped.
- Use the full score range; `possible` gives each item's maximum.
"""


def write_bundle(bundle: dict, forllm_dir: str, ai_ta_name: str = "your AI teaching assistant"):
    """Write the JSON bundle + the contract text into the ForLLM folder. Returns
    (bundle_path, contract_path)."""
    os.makedirs(forllm_dir, exist_ok=True)
    stem = _safe(bundle.get("quiz_title", "quiz"))
    bpath = os.path.join(forllm_dir, f"{stem}__bundle.json")
    cpath = os.path.join(forllm_dir, f"{stem}__HOW-TO-SCORE.txt")
    with open(bpath, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, ensure_ascii=False)
    with open(cpath, "w", encoding="utf-8") as f:
        f.write(build_contract_text(ai_ta_name))
    return bpath, cpath


# --------------------------------------------------------------------------
# Re-identify LLM results
# --------------------------------------------------------------------------

def parse_results(text: str) -> list:
    """Parse the LLM's result JSON (an array, or an object wrapping `results`)."""
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("results", [])
    return data if isinstance(data, list) else []


def reidentify(results: list, vault: Vault) -> list:
    """Map pseudonymous results back to real students via the vault. Unknown
    pseudonyms are marked `resolved: False` rather than dropped."""
    out = []
    for r in results:
        who = vault.reverse(r.get("pseudonym", ""))
        out.append({
            "resolved":  who is not None,
            "real_name": (who or {}).get("real_name", ""),
            "canvas_id": (who or {}).get("canvas_id", ""),
            "sis_id":    (who or {}).get("sis_id", ""),
            "item_id":   r.get("item_id", ""),
            "score":     r.get("score"),
            "feedback":  r.get("feedback", ""),
            "disclosure": r.get("disclosure", ""),
        })
    return out


def reidentified_csv(rows: list) -> str:
    """Render re-identified results as CSV text (for the ToEnter folder)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Student", "Canvas ID", "SIS ID", "Item", "Score", "Feedback", "Disclosure"])
    for r in rows:
        w.writerow([r["real_name"], r["canvas_id"], r["sis_id"], r["item_id"],
                    "" if r["score"] is None else r["score"], r["feedback"], r["disclosure"]])
    return buf.getvalue()


# --------------------------------------------------------------------------
# Drop-folder workflow
# --------------------------------------------------------------------------

def process_inbox(inbox_dir, forllm_dir, archive_dir, vault, ai_ta_name="your AI teaching assistant"):
    """Generator of progress strings. Process every CSV in 1_Inbox -> pseudonymized
    bundle in 2_ForLLM, then archive the original. Saves the vault."""
    import glob
    import shutil
    os.makedirs(archive_dir, exist_ok=True)
    csvs = sorted(glob.glob(os.path.join(inbox_dir, "*.csv"))) if os.path.isdir(inbox_dir) else []
    if not csvs:
        yield "No CSVs in the Inbox."
        return
    for path in csvs:
        title = os.path.splitext(os.path.basename(path))[0]
        try:
            parsed = parse_student_analysis_file(path)
            bundle = pseudonymize(parsed, vault, title)
            write_bundle(bundle, forllm_dir, ai_ta_name)
            shutil.move(path, os.path.join(archive_dir, os.path.basename(path)))
            yield f"✓ {title}: {len(bundle['students'])} student(s) pseudonymized → ForLLM"
        except Exception as e:
            yield f"!! {title}: {e}"
    vault.save()
    yield f"FOLDER: {forllm_dir}"


def reidentify_dir(fromllm_dir, toenter_dir, vault):
    """Generator of progress strings. Re-identify every results file in 3_FromLLM ->
    a real-name CSV in 4_ToEnter."""
    import glob
    os.makedirs(toenter_dir, exist_ok=True)
    files = (sorted(glob.glob(os.path.join(fromllm_dir, "*.json")))
             if os.path.isdir(fromllm_dir) else [])
    if not files:
        yield "No result files in FromLLM."
        return
    for path in files:
        stem = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, encoding="utf-8") as f:
                rows = reidentify(parse_results(f.read()), vault)
            dest = os.path.join(toenter_dir, f"{stem}__to-enter.csv")
            with open(dest, "w", encoding="utf-8", newline="") as f:
                f.write(reidentified_csv(rows))
            unresolved = sum(1 for r in rows if not r["resolved"])
            note = f" ({unresolved} unmatched)" if unresolved else ""
            yield f"✓ {stem}: {len(rows)} result(s) re-identified{note}"
        except Exception as e:
            yield f"!! {stem}: {e}"
    yield f"FOLDER: {toenter_dir}"
