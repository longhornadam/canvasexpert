"""Build merged, chronological writing portfolios (one DOCX per student).

Combines, per student:
  - New Quizzes constructed responses (from an uploaded Student Analysis CSV), and
  - Canvas Assignment text entries + uploaded files/photos (live core API).

Live, token-holding (like student_packet.py). Downloaded attachments are written to a
temp dir, embedded, then removed — only the per-student DOCX persists, in the FERPA-safe
Student Reports root. NEVER writes student data into the repo.
"""
import os
import shutil
import tempfile
from datetime import datetime

import requests

from api import portfolio, report_local_reads
from api.submission_transport import download_binary, fetch_submission, get_all_pages
from api.webui.workspace import safe_component

safe_name = safe_component
_download_binary = download_binary
_fetch_submission = fetch_submission
_get_all_pages = get_all_pages


def _assignment_entries(subs, session, work_dir, date_from, date_to):
    """Turn a student's submissions into portfolio entries, downloading attachments
    into work_dir for embedding. Skips submissions with no writing/attachment."""
    entries = []
    for s in subs:
        a = s.get("assignment") or {}
        body = portfolio.html_to_text(s.get("body") or "")
        att_meta = s.get("attachments") or []
        if not body and not att_meta:
            continue
        date = ((s.get("submitted_at") or a.get("due_at") or "") or "")[:10]
        if date_from and date and date < date_from:
            continue
        if date_to and date and date > date_to:
            continue
        local = []
        for att in att_meta:
            orig = att.get("filename") or att.get("display_name") or "file"
            dest = os.path.join(work_dir, safe_name(f"{a.get('id','')}-{orig}"))
            ext = os.path.splitext(orig)[1]
            if ext and not dest.endswith(ext):
                dest += ext
            try:
                _download_binary(session, att["url"], dest)
                local.append(dest)
            except Exception:
                pass  # rendering will simply omit a missing file
        entries.append({
            "date": date, "source": "Assignment", "title": a.get("name", "Assignment"),
            "prompt": portfolio.html_to_text(a.get("description") or ""),
            "response_text": body, "attachments": local,
            "earned": s.get("score"), "possible": a.get("points_possible"),
        })
    return entries


def build_merged_portfolios(course, students, parsed_nq, quiz_title,
                            base, token, reports_root,
                            date_from=None, date_to=None):
    """Generator of progress strings. `students` = [{id, name}]. `parsed_nq` may be
    None (assignments only) or a parsed Student Analysis dict (matched by Canvas id).
    Final line: 'FOLDER: <reports_root>'."""
    session_box: dict = {}

    def _session():
        # Constructed only the first time a live fallback fetch, a focused
        # attachment fetch, or an attachment download actually needs it.
        if "session" not in session_box:
            live = requests.Session()
            live.headers["Authorization"] = f"Bearer {token}"
            session_box["session"] = live
        return session_box["session"]

    cid = str(course["id"])
    # One local read for the whole course, before the per-student loop — not
    # once per student. `None` means the course isn't local-current; every
    # student then falls back to today's existing per-student live fetch.
    local_by_user = report_local_reads.local_course_submissions_by_user(cid)
    used_local = local_by_user is not None
    # Private, non-rendered source/freshness disclosure for this single course
    # — read once, independent of `local_by_user`'s own gate/return value.
    freshness = report_local_reads.local_course_freshness(cid)
    nq_map = {}
    if parsed_nq:
        nq_map = {str(s.get("canvas_id")): s for s in parsed_nq.get("students", [])}

    work_root = tempfile.mkdtemp(prefix="ce_portfolio_")
    made = 0
    try:
        for stu in students:
            uid, name = str(stu["id"]), stu["name"]
            if used_local:
                subs = local_by_user.get(uid, [])
                # The local path never stores attachments (signed URLs are
                # never cached) — a focused, single-submission live call is
                # the only way to learn whether an online_upload submission
                # has files, and only for that one submission, never the
                # whole course.
                for record in subs:
                    if record.get("submission_type") == "online_upload":
                        fetched = _fetch_submission(
                            _session(), base, cid, record.get("assignment_id"), uid)
                        if fetched:
                            record["attachments"] = fetched.get("attachments") or []
            else:
                try:
                    subs = _get_all_pages(
                        _session(), f"{base}/api/v1/courses/{cid}/students/submissions",
                        {"student_ids[]": uid, "include[]": ["assignment"], "per_page": 100})
                except Exception as e:
                    yield f"· {name}: skipped ({e})"
                    continue
            work_dir = os.path.join(work_root, uid)
            os.makedirs(work_dir, exist_ok=True)
            entries = _assignment_entries(subs or [], _session(), work_dir, date_from, date_to)
            nqs = nq_map.get(uid)
            if nqs:
                entries += portfolio.nq_entries(parsed_nq, nqs, quiz_title or "New Quiz")
            if not entries:
                yield f"· {name}: no writing found — skipped"
                continue
            stu_dir = os.path.join(reports_root, safe_name(name))
            dest = os.path.join(stu_dir, f"{safe_name(name)} - Writing Portfolio.docx")
            portfolio.render_merged_docx(name, entries, dest)
            made += 1
            # Only for a student whose portfolio was actually produced — not
            # for a "no writing found" skip, which yields no output at all.
            report_local_reads.write_source_manifest(stu_dir, {
                cid: {
                    "course_name": course.get("name", ""),
                    "source": freshness["source"],
                    "synced_at": freshness["synced_at"],
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                },
            })
            yield f"✓ {name}: {len(entries)} item(s)"
    finally:
        shutil.rmtree(work_root, ignore_errors=True)

    yield f"Created {made} portfolio(s)."
    yield f"FOLDER: {reports_root}"
