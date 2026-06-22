"""FeedbackExpert pipeline: pseudonymize student work, emit an LLM-ready scoring
bundle, and re-identify the LLM's results back to real students via the vault.

Pure-ish stdlib + the NQ parser. Offline-testable. Only pseudonymized payloads are
ever written to the SAFE folder; real identities live only in the vault and PRIVATE
folder.
"""
import csv
import io
import json
import os

try:                                   # script context (run from api/)
    from nq_report import constructed_responses, html_to_text, parse_student_analysis_file
    from feedback_vault import Vault
    import feedback_scrub
    import feedback_safety
except ModuleNotFoundError:            # package context (tests: api.feedback_pipeline)
    from api.nq_report import constructed_responses, html_to_text, parse_student_analysis_file
    from api.feedback_vault import Vault
    from api import feedback_scrub
    from api import feedback_safety

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

    # Roster tokens for collision-safe fake-name assignment: a fake name must not
    # match any real first/last token in this batch (otherwise the scrub's chained
    # replacement can cross-link students). The Name Manager roster sync does this
    # too; we repeat it here so the guided flow is correct even without a prior sync.
    roster_tokens: set = set()
    for entry in by_student.values():
        for t in (entry.get("real_name") or "").split():
            roster_tokens.add(t.lower())

    students = []
    for uid, entry in by_student.items():
        pseudo = vault.get_or_assign(uid, entry["real_name"], entry["sis_id"],
                                     roster_names=roster_tokens)
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


def build_contract_text(ai_ta_name: str = "your AI teaching assistant",
                        rubric_text: str = "") -> str:
    """Instructions the teacher pastes into their LLM alongside the bundle. When
    `rubric_text` is provided it is inlined below so the file is self-contained
    (prompt context lives in the bundle; the rubric travels here) — no separate
    attach step. When omitted, the older "attach the rubric as Knowledge" wording
    is used (the parked NQ / OpenRouter lanes supply the rubric separately).
    Extends the Essay Scorer skill: keyed batch output for automatic
    re-identification, with mandatory disclosure naming the AI-TA."""
    if rubric_text.strip():
        rubric_clause = ("The scoring rubric is included at the bottom of this file "
                         "— score strictly by it, do not invent criteria.")
        rubric_block = f"\n\n--- RUBRIC (score strictly by this) ---\n{rubric_text.strip()}\n"
    else:
        rubric_clause = ("A RubricForge rubric is attached as Knowledge — score "
                         "strictly by it, do not invent criteria.")
        rubric_block = ""
    return f"""You are {ai_ta_name}, an AI teaching assistant helping a real teacher
score student writing and draft feedback. {rubric_clause}

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
- Use the full score range; `possible` gives each item's maximum.{rubric_block}"""


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
# Scrub-integrated SAFE / PRIVATE writing (v2 pipeline)
# --------------------------------------------------------------------------

def _scrub_bundle(bundle: dict, vault: Vault,
                  protected: set[str] | None = None) -> dict:
    """Deep-scrub every text field in a bundle. Returns a new bundle dict
    with prompts and responses scrubbed."""
    rmap = feedback_scrub.build_replacement_map(vault.entries(),
                                                protected or set())
    import copy
    out = copy.deepcopy(bundle)
    for s in out.get("students", []):
        for r in s.get("responses", []):
            if r.get("prompt"):
                r["prompt"] = feedback_scrub.scrub_text(r["prompt"], rmap)
            if r.get("response"):
                r["response"] = feedback_scrub.scrub_text(r["response"], rmap)
    return out


def write_safe_and_private(
    bundle: dict,
    vault: Vault,
    safe_dir: str,
    private_dir: str,
    ai_ta_name: str = "your AI teaching assistant",
    protected: set[str] | None = None,
    submissions: list | None = None,
    rubric_text: str = "",
) -> dict:
    """Write a scrubbed SAFE bundle + unscrubbed PRIVATE copy + who-is-who.

    1. Deep-scrub every prompt/response using the vault name map + protected set.
    2. Run assert_scrubbed — green required.
    3. Write SAFE/ bundle (assignment title named) + per-student .txt files
       named with pseudonym.
    4. Write PRIVATE/ raw bundle + who-is-who.csv.
    5. Track attachment-only submissions (excluded from SAFE).

    Returns {
        "safe_bundle": path,
        "safe_students": n,
        "private_bundle": path,
        "who_is_who": path,
        "student_txts": [path, ...],
        "attachment_only": [submission_info, ...],
        "log": [str, ...],
    }
    """
    os.makedirs(safe_dir, exist_ok=True)
    os.makedirs(private_dir, exist_ok=True)
    log: list[str] = []
    attachment_only: list[dict] = []
    excluded: list[str] = []
    stem = _safe(bundle.get("quiz_title", "assignment"))

    # Step 1: scrub
    safe = _scrub_bundle(bundle, vault, protected=protected)

    # Step 2: assert_scrubbed receipt — structural HARD gate (forbidden identity
    # keys / raw ids). A correctly built bundle never trips this; it catches a
    # raw payload reaching the writer at all.
    receipt = feedback_safety.assert_scrubbed(safe, vault)
    if not receipt["green"]:
        log.append(f"!! SAFETY BLOCK — hard violations in {stem}: {receipt['hard'][:3]}")
        return {"safe_bundle": None, "safe_students": 0, "private_bundle": None,
                "who_is_who": None, "student_txts": [],
                "attachment_only": [], "excluded": [], "log": log}

    # Step 2b: per-student verify gate (the real receipt). Word-boundary re-scan of
    # each scrubbed student against EVERY real identifier the vault knows. A survivor
    # means the scrub missed a real name — we PULL that student from SAFE entirely
    # (they stay in PRIVATE for manual scoring) rather than write a real name into a
    # "safe" file. Never block the whole batch; never leak.
    clean_students = []
    for s in safe.get("students", []):
        blob = " ".join((r.get("prompt") or "") + " " + (r.get("response") or "")
                        for r in s.get("responses", []))
        survivors = feedback_scrub.verify_clean(blob, vault)
        if survivors:
            excluded.append(s.get("pseudonym", "?"))
            log.append(f"!! EXCLUDED {s.get('pseudonym','?')} from SAFE — scrub left a "
                       f"real identifier ({len(survivors)} hit); score this one manually.")
        else:
            clean_students.append(s)
    safe["students"] = clean_students

    # Step 3: identify attachment-only submissions
    if submissions:
        for s in submissions:
            body = s.get("body") or ""
            if not body.strip() and (s.get("attachments") or []):
                user = s.get("user") or {}
                attachment_only.append({
                    "user_id": s.get("user_id"),
                    "name": user.get("name") or "",
                    "urls": [a.get("url") for a in s.get("attachments", []) if a.get("url")],
                })

    # Step 4: write SAFE bundle
    bpath = os.path.join(safe_dir, f"{stem}__bundle.json")
    with open(bpath, "w", encoding="utf-8") as f:
        json.dump(safe, f, indent=2, ensure_ascii=False)
    # Write HOW-TO-SCORE.txt — rubric inlined so the file is self-contained for the
    # teacher's own LLM (prompt context lives in the bundle; rubric travels here).
    cpath = os.path.join(safe_dir, f"{stem}__HOW-TO-SCORE.txt")
    with open(cpath, "w", encoding="utf-8") as f:
        f.write(build_contract_text(ai_ta_name, rubric_text=rubric_text))
    log.append(f"✓ {stem}: SAFE bundle ({len(safe['students'])} student(s))")

    # Step 5: per-student .txt files named with pseudonym
    student_txts: list[str] = []
    for s in safe.get("students", []):
        pseudo = s.get("pseudonym", "unknown")
        safe_name = pseudo.replace(" ", "-")
        txt_path = os.path.join(safe_dir, f"{safe_name}__SAFE.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"Pseudonym: {pseudo}\n")
            f.write(f"Assignment: {stem}\n")
            f.write(f"{'='*50}\n\n")
            for r in s.get("responses", []):
                if r.get("prompt"):
                    f.write(f"Prompt:\n{r['prompt']}\n\n")
                if r.get("response"):
                    f.write(f"Response:\n{r['response']}\n\n")
        student_txts.append(txt_path)
    log.append(f"✓ {stem}: {len(student_txts)} per-student SAFE .txt file(s)")

    # Step 6: write PRIVATE raw bundle
    priv_path = os.path.join(private_dir, f"{stem}__PRIVATE.json")
    with open(priv_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, ensure_ascii=False)
    log.append(f"✓ {stem}: PRIVATE raw bundle saved")

    # Step 7: write who-is-who.csv to PRIVATE (all vault entries for context)
    who_path = os.path.join(private_dir, f"{stem}__who-is-who.csv")
    with open(who_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Real Name", "Canvas ID", "SIS ID", "Pseudonym", "Nicknames"])
        for e in vault.entries():
            w.writerow([
                e.get("real_name", ""),
                e.get("canvas_id", ""),
                e.get("sis_id", ""),
                e.get("pseudonym", ""),
                ", ".join(e.get("nicknames", [])),
            ])
    log.append(f"✓ {stem}: who-is-who.csv saved")

    return {
        "safe_bundle": bpath,
        "safe_students": len(safe.get("students", [])),
        "private_bundle": priv_path,
        "who_is_who": who_path,
        "student_txts": student_txts,
        "attachment_only": attachment_only,
        "excluded": excluded,
        "log": log,
    }


# --------------------------------------------------------------------------
# Re-identify LLM results
# --------------------------------------------------------------------------

def parse_results(text: str) -> list:
    """Parse the LLM's result JSON (an array, or an object wrapping `results`)."""
    data = json.loads(text)
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
        if not r.get("disclosure"):
            warnings.append(f"{where}: missing 'disclosure' line")
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
