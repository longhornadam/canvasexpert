"""Feedback tools bundle and artifact writing helpers."""
import csv
import json
import os

try:                                   # script context (run from api/)
    from nq_report import constructed_responses, html_to_text, parse_student_analysis_file
    from feedback_vault import Vault
    import feedback_scrub
    import feedback_safety
    from powergrader import student_attachments
except ModuleNotFoundError:            # package context (tests: api.feedback_artifacts)
    from api.nq_report import constructed_responses, html_to_text, parse_student_analysis_file
    from api.feedback_vault import Vault
    from api import feedback_scrub
    from api import feedback_safety
    from api.powergrader import student_attachments

try:
    from feedback_contract import (
        CONTRACT_VERSION,
        _REVIEW_NOTE,
        _safe,
        build_contract_text,
    )
except ModuleNotFoundError:
    from api.feedback_contract import (
        CONTRACT_VERSION,
        _REVIEW_NOTE,
        _safe,
        build_contract_text,
    )

try:
    from feedback_results import parse_results, reidentify, reidentified_csv
except ModuleNotFoundError:
    from api.feedback_results import parse_results, reidentify, reidentified_csv


def _attachment_meta(attachment: dict) -> dict:
    """Copy local evidence metadata without any URL/token-bearing fields."""
    allowed = {
        "filename", "display_name", "local_path", "declared_size", "actual_size", "size",
        "detected_media_type", "media_type", "download_status", "extraction_status",
        "extracted_text_path", "attempt", "item_id", "item_link", "ai_eligible",
        "local_only", "warnings", "error_code", "error_message",
    }
    return {k: attachment.get(k) for k in allowed if k in attachment}


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


def _is_upload_item(item: dict) -> bool:
    kind = str(item.get("type") or "").lower().replace("-", "_")
    return "upload" in kind


def _extracted_upload_text(files: list) -> str | None:
    """Join locally-extracted text for one item's uploads.

    Returns None unless EVERY upload on the item has readable local text —
    a partially-readable upload item must not be scored as if it were complete.
    """
    texts = []
    for file in files or []:
        if not isinstance(file, dict):
            return None
        path = file.get("extracted_text_path")
        text = ""
        if path and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read().strip()
            except OSError:
                text = ""
        if not text:
            return None
        texts.append(f"[Uploaded file text: {file.get('filename') or 'upload'}]\n{text}")
    return "\n\n".join(texts) if texts else None


def _new_quiz_ai_response(item: dict) -> dict | None:
    """Map one New Quiz item to an AI-scorable response, or None to keep it local.

    File-upload items are never sent as files or filenames: a TXT/DOCX-style
    upload with locally-extracted text is packaged like an essay response;
    anything else (image, PDF, PPTX, failed download) is excluded from the AI
    payload entirely and stays in the local queue for teacher review.
    """
    if _is_upload_item(item):
        response_text = _extracted_upload_text(item.get("files"))
        if response_text is None:
            return None
    else:
        response_text = html_to_text(item.get("raw_html_answer") or "")
        extra = _extracted_upload_text(item.get("files"))
        if extra:
            response_text = "\n\n".join(part for part in (response_text, extra) if part)
    return {
        "item_id": str(item.get("item_id") or ""),
        "prompt": html_to_text(item.get("prompt") or ""),
        "response": response_text,
        "possible": item.get("possible"),
    }


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
        new_quiz_items = s.get("new_quiz_items") or []
        attachment_values = [
            _attachment_meta(a) for a in (s.get("attachments") or [])
            if isinstance(a, dict) and (a.get("local_path") or a.get("download_status"))
        ]
        if new_quiz_items:
            existing = by_student.get(uid)
            if existing is None:
                # New Quiz uploads never enter the AI lane as files: readable
                # local text is inlined per item below, everything else stays
                # local-only for teacher review. No attachments, no media.
                by_student[uid] = {
                    "responses": [], "attachments": [],
                    "real_name": user.get("name") or user.get("sortable_name") or "",
                    "sis_id": str(user.get("sis_user_id") or ""),
                    "_expected_attachment_count": 0,
                }
            by_student[uid]["responses"] = [
                entry for entry in (_new_quiz_ai_response(item) for item in new_quiz_items)
                if entry is not None
            ]
            continue
        prompt = html_to_text(a.get("description") or "")
        body_text = html_to_text(s.get("body") or "")
        # Plain-text code-file uploads (.py/.html/...) are folded in as RAW text —
        # never html_to_text'd, or an HTML submission's tags (the thing being graded)
        # would be stripped. The route fetches these into s["code_files"].
        code_files = s.get("code_files") or []
        # ``code_files`` is a legacy read path only.  New ordinary ingestion
        # routes every attachment through local_attachments exactly once.
        normalized_attachments = any(
            isinstance(attachment, dict) and ("download_status" in attachment or attachment.get("local_path"))
            for attachment in (s.get("attachments") or [])
        )
        code_text = "" if normalized_attachments else "\n\n".join(
            f"--- {cf.get('filename', 'file')} ---\n{cf.get('text', '')}"
            for cf in code_files if cf.get("text")
        )
        response = "\n\n".join(p for p in (body_text, code_text) if p).strip()
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
            "attachments": attachment_values,
            "_expected_attachment_count": s.get("expected_attachment_count", len(attachment_values)),
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
        if "responses" in entry and not entry["responses"]:
            # New Quiz student whose only items were excluded from the AI lane
            # (e.g. image/PDF uploads): keep them out of the packet entirely.
            continue
        pseudo = vault.get_or_assign(uid, entry["real_name"], entry["sis_id"],
                                     roster_names=roster_tokens)
        responses = entry.get("responses") or [{
            "item_id":  entry["item_id"],
            "prompt":   entry["prompt"],
            "response": entry["response"],
            "possible": entry["possible"],
        }]
        students.append({
            "pseudonym": pseudo,
            "responses": responses,
            "local_attachments": entry.get("attachments") or [],
            "_expected_attachment_count": entry.get("_expected_attachment_count", 0),
        })

    return {"contract_version": CONTRACT_VERSION,
            "quiz_title": assignment_title,
            "source": "assignment",
            "review_required": True, "note": _REVIEW_NOTE, "students": students}


def write_bundle(bundle: dict, forllm_dir: str, ai_ta_name: str = "your teaching assistant",
                 persona: dict | None = None):
    """Write the JSON bundle + the contract text into the ForLLM folder. Returns
    (bundle_path, contract_path)."""
    os.makedirs(forllm_dir, exist_ok=True)
    stem = _safe(bundle.get("quiz_title", "quiz"))
    bpath = os.path.join(forllm_dir, f"{stem}__bundle.json")
    cpath = os.path.join(forllm_dir, f"{stem}__HOW-TO-SCORE.txt")
    with open(bpath, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, ensure_ascii=False)
    with open(cpath, "w", encoding="utf-8") as f:
        f.write(build_contract_text(ai_ta_name, persona=persona))
    return bpath, cpath


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
    shared = out.get("shared_context")
    if isinstance(shared, dict):
        if shared.get("assignment_description"):
            shared["assignment_description"] = feedback_scrub.scrub_text(
                shared.get("assignment_description") or "", rmap
            )
        for material in shared.get("materials") or []:
            if isinstance(material, dict) and material.get("text"):
                material["text"] = feedback_scrub.scrub_text(material.get("text") or "", rmap)
    return out


def _prepare_attachment_safe_bundle(bundle: dict, safe_dir: str) -> tuple[dict, list[str], list[str]]:
    """Convert downloaded local evidence into safe text/media or hold the student."""
    import copy

    out = copy.deepcopy(bundle)
    excluded: list[str] = []
    log: list[str] = []
    kept_students = []
    for student in out.get("students") or []:
        attachments = [a for a in student.get("local_attachments") or [] if isinstance(a, dict)]
        if not attachments:
            student.pop("local_attachments", None)
            student.pop("_expected_attachment_count", None)
            kept_students.append(student)
            continue
        expected_count = student.get("_expected_attachment_count", len(attachments))
        decision = student_attachments.eligibility_decision(attachments, expected_count=expected_count)
        pseudo = student.get("pseudonym") or "unknown"
        if not decision["eligible"]:
            excluded.append(pseudo)
            log.append(f"!! HELD {pseudo} — attachment evidence needs teacher review: {decision['reasons'][0]}")
            continue
        media_dir = os.path.join(safe_dir, "Students", pseudo.replace(" ", "-"))
        for index, attachment in enumerate(attachments, start=1):
            local_path = attachment.get("local_path")
            if not local_path or not os.path.isfile(local_path):
                excluded.append(pseudo)
                log.append(f"!! HELD {pseudo} — downloaded attachment is no longer available locally")
                break
            try:
                with open(local_path, "rb") as source:
                    raw_attachment = source.read()
                routed = student_attachments.route_bytes(
                    f"attachment-{index}{os.path.splitext(attachment.get('filename') or '')[1]}",
                    raw_attachment,
                )
            except Exception as exc:
                excluded.append(pseudo)
                log.append(f"!! HELD {pseudo} — attachment validation failed ({type(exc).__name__})")
                break
            routed_decision = student_attachments.eligibility_decision([routed])
            if not routed_decision["eligible"]:
                excluded.append(pseudo)
                log.append(
                    f"!! HELD {pseudo} — attachment evidence changed or failed validation "
                    f"({routed_decision['reasons'][0]})"
                )
                break
            for response in student.get("responses") or []:
                if attachment.get("item_id") and str(response.get("item_id")) != str(attachment.get("item_id")):
                    continue
                if routed.get("text"):
                    response["response"] = (response.get("response") or "") + "\n\n" + (
                        f"Attachment {index} text:\n{routed['text']}"
                    )
                for output in student_attachments.write_safe_derivatives(
                    routed, media_dir, pseudonym=pseudo, item_id=attachment.get("item_id") or index
                ):
                    response.setdefault("media", []).append({
                        "item_id": str(attachment.get("item_id") or ""),
                        "filename": f"attachment-{index}",
                        "local_path": output["local_path"],
                        "media_type": output["media_type"],
                    })
        student.pop("local_attachments", None)
        student.pop("_expected_attachment_count", None)
        if pseudo not in excluded:
            kept_students.append(student)
    out["students"] = kept_students
    return out, excluded, log


def _shared_context_blob(shared) -> str:
    if not isinstance(shared, dict):
        return ""
    chunks = []
    if shared.get("assignment_description"):
        chunks.append(str(shared.get("assignment_description") or ""))
    for material in shared.get("materials") or []:
        if isinstance(material, dict):
            chunks.append(str(material.get("text") or ""))
    return "\n\n".join(chunks)


def write_safe_and_private(
    bundle: dict,
    vault: Vault,
    safe_dir: str,
    private_dir: str,
    ai_ta_name: str = "your teaching assistant",
    persona: dict | None = None,
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
    shared_context_excluded = False
    stem = _safe(bundle.get("quiz_title", "assignment"))

    # Step 1: convert approved local evidence, then scrub text.
    prepared, attachment_excluded, attachment_log = _prepare_attachment_safe_bundle(bundle, safe_dir)
    excluded.extend(attachment_excluded)
    log.extend(attachment_log)
    safe = _scrub_bundle(prepared, vault, protected=protected)

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

    shared_blob = _shared_context_blob(safe.get("shared_context"))
    if shared_blob:
        shared_survivors = feedback_scrub.verify_clean(shared_blob, vault)
        if shared_survivors:
            safe.pop("shared_context", None)
            shared_context_excluded = True
            log.append(
                f"!! EXCLUDED shared source context from SAFE — scrub left a real "
                f"identifier ({len(shared_survivors)} hit)."
            )

    # Step 3: identify submissions we still can't score — no text body AND no
    # plain-text code files, but some attachment (image/PDF/DOCX). Code-file uploads
    # ARE scored (folded into the response above), so they are NOT flagged here.
    if submissions:
        for s in submissions:
            body = s.get("body") or ""
            has_code = bool(s.get("code_files"))
            non_code = [a for a in (s.get("attachments") or [])
                        if not a.get("ai_eligible") or a.get("download_status") != "downloaded"]
            if not body.strip() and not has_code and non_code:
                user = s.get("user") or {}
                attachment_only.append({
                    "user_id": s.get("user_id"),
                    "name": user.get("name") or "",
                    "attachment_count": len(non_code),
                    "filenames": [a.get("filename") or a.get("display_name") or "attachment"
                                  for a in non_code],
                })

    # Step 4: write SAFE bundle
    bpath = os.path.join(safe_dir, f"{stem}__bundle.json")
    with open(bpath, "w", encoding="utf-8") as f:
        json.dump(safe, f, indent=2, ensure_ascii=False)
    # Write HOW-TO-SCORE.txt — rubric inlined so the file is self-contained for the
    # teacher's own LLM (prompt context lives in the bundle; rubric travels here).
    cpath = os.path.join(safe_dir, f"{stem}__HOW-TO-SCORE.txt")
    with open(cpath, "w", encoding="utf-8") as f:
        f.write(build_contract_text(ai_ta_name, rubric_text=rubric_text, persona=persona))
    log.append(f"✓ {stem}: SAFE bundle ({len(safe['students'])} student(s))")

    shared_context_path = None
    shared = safe.get("shared_context")
    if isinstance(shared, dict) and (
        shared.get("assignment_description") or shared.get("materials")
    ):
        shared_context_path = os.path.join(safe_dir, f"{stem}__SHARED-CONTEXT.txt")
        with open(shared_context_path, "w", encoding="utf-8") as f:
            f.write(f"Assignment: {stem}\n")
            f.write(f"{'='*50}\n\n")
            if shared.get("assignment_description"):
                f.write("Assignment directions/context:\n")
                f.write(str(shared.get("assignment_description") or ""))
                f.write("\n\n")
            for material in shared.get("materials") or []:
                if not isinstance(material, dict):
                    continue
                f.write(f"Source material: {material.get('title') or 'Untitled'}\n")
                if material.get("source"):
                    f.write(f"From: {material.get('source')}\n")
                f.write("-" * 50)
                f.write("\n")
                f.write(str(material.get("text") or ""))
                f.write("\n\n")
        log.append(f"✓ {stem}: SAFE shared context file saved")

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
        "how_to_score": cpath,
        "student_txts": student_txts,
        "shared_context": shared_context_path,
        "shared_context_excluded": shared_context_excluded,
        "attachment_only": attachment_only,
        "excluded": excluded,
        "log": log,
    }


def process_inbox(inbox_dir, forllm_dir, archive_dir, vault, ai_ta_name="your teaching assistant"):
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
