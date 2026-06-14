"""Student Reports — compile one student's work + standing into a local packet.

Folder layout, per student, per course:  <root>/<Student>/<Course>/{Assignments,Info}
Neutral, label-free output (see SPEC_Student_Reports Language rules). Local-only.
"""
import json
import os
from datetime import datetime

import requests
from docx import Document

from downloader import _download_binary, safe_name, _get_all_pages

# Section keys the UI offers (order preserved in the document):
SECTIONS = ["standing", "late", "adjustments", "comments", "work"]

DOWNLOADABLE = {"online_text_entry", "online_upload", "online_url"}


# ── DOCX ─────────────────────────────────────────────────────────────────


def _render_info_docx(dest, student_name, course_name, blocks):
    """blocks: ordered list of (heading, kind, payload):
       kind 'table' → payload {cols:[...], rows:[[...]]}; kind 'lines' → [str]."""
    doc = Document()
    doc.add_heading(student_name, level=0)
    doc.add_paragraph(f"{course_name} · generated {datetime.now():%b %d, %Y}")
    for heading, kind, payload in blocks:
        doc.add_heading(heading, level=2)
        if kind == "table" and payload and payload["rows"]:
            cols = payload["cols"]
            t = doc.add_table(rows=1, cols=len(cols))
            t.style = "Light Grid Accent 1"
            for i, c in enumerate(cols):
                t.rows[0].cells[i].text = str(c)
            for row in payload["rows"]:
                cells = t.add_row().cells
                for i, val in enumerate(row):
                    cells[i].text = "" if val is None else str(val)
        elif kind == "lines" and payload:
            for ln in payload:
                doc.add_paragraph(ln, style="List Bullet")
        else:
            doc.add_paragraph("None on record.")
    doc.save(dest)


# ── Data shaping (neutral language lives HERE) ──────────────────────────────


def _days_late(seconds):
    try:
        return max(1, round(int(seconds) / 86400))
    except (TypeError, ValueError):
        return None


def _info_blocks(subs, curve_rows, sections):
    standing, late, adj, comments = [], [], [], []
    for s in subs:
        a = s.get("assignment") or {}
        name = a.get("name", "?")
        pts = a.get("points_possible", "")
        state = "Excused" if s.get("excused") else (s.get("workflow_state") or "")
        standing.append([name, str(pts),
                         str(s.get("score", "") if s.get("score") is not None else ""),
                         state, (s.get("submitted_at") or "")[:10]])
        # late / extended due date — factual, no "accommodation"
        if s.get("excused"):
            late.append(f'{name}: Excused')
        else:
            base_due = (a.get("due_at") or "")[:10]
            cached_due = (s.get("cached_due_date") or "")[:10]
            if cached_due and base_due and cached_due > base_due:
                late.append(f'{name}: Due date extended to {cached_due}')
            if s.get("late") and s.get("seconds_late"):
                d = _days_late(s["seconds_late"])
                if d:
                    late.append(f'{name}: Submitted {d} day(s) late')
        for c in (s.get("submission_comments") or []):
            who = (c.get("author_name") or "").strip()
            when = (c.get("created_at") or "")[:10]
            comments.append(f'{when} — {who}: {c.get("comment", "")}')
    for cr in curve_rows:
        adj.append(cr)   # pre-formatted neutral strings, built in build_packet
    blocks = []
    if "standing" in sections:
        blocks.append(("Standing", "table",
                       {"cols": ["Assignment", "Pts Available", "Score", "Status", "Submitted"],
                        "rows": standing}))
    if "late" in sections:
        blocks.append(("Late & extended due dates", "lines", late))
    if "adjustments" in sections:
        blocks.append(("Adjustments", "lines", adj))
    if "comments" in sections:
        blocks.append(("Comments", "lines", comments))
    return blocks


def _signature(subs, curve_rows):
    """Cheap change-detector for dedupe: latest activity + counts."""
    last = max([(s.get("submitted_at") or "") for s in subs] + [""])
    graded = sum(1 for s in subs if s.get("workflow_state") == "graded")
    return f"{last}|{graded}|{len(curve_rows)}"


# ── Per-student build ───────────────────────────────────────────────────────


def build_packet(user_id, student_name, sections, courses, base, token,
                 reports_root, curve_events, skip_unchanged=False):
    """Generator of progress strings. `courses` = [{id, name}] to consider.
    Final line: 'FOLDER: <student root>'. Set skip_unchanged for the routine path."""
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"
    stu_root = os.path.join(reports_root, safe_name(student_name))
    os.makedirs(stu_root, exist_ok=True)
    man_path = os.path.join(stu_root, "_manifest.json")
    try:
        with open(man_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception:
        manifest = {}

    yield f"Student: {student_name}"
    any_course = False
    for c in courses:
        cid, cname = str(c["id"]), c["name"]
        try:
            subs = _get_all_pages(
                session, f"{base}/api/v1/courses/{cid}/students/submissions",
                {"student_ids[]": str(user_id),
                 "include[]": ["assignment", "submission_comments"],
                 "per_page": 100})
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            yield f"· {cname}: no access (HTTP {code}) — skipped"
            continue                         # e.g. 403 where the teacher can't read submissions
        except Exception as e:
            yield f"· {cname}: skipped ({e})"
            continue
        subs = [s for s in (subs or []) if (s.get("assignment") or {}).get("id")]
        if not subs:
            continue                         # student not in this course
        any_course = True
        # curve adjustments for this student+course (local records, neutral phrasing)
        curve_rows = []
        for ev in curve_events:
            if str(ev.get("course_id")) != cid or ev.get("reverted"):
                continue
            for st in (ev.get("students") or []):
                if str(st.get("user_id")) == str(user_id):
                    old, new = st.get("original_score"), st.get("curved_score")
                    when = (ev.get("applied_at") or "")[:10]
                    curve_rows.append(
                        f'{ev.get("assignment_name", ev.get("assignment_id"))}: '
                        f'Score adjusted via curve on {when}: {old} → {new}')

        sig = _signature(subs, curve_rows)
        if skip_unchanged and manifest.get(cid, {}).get("signature") == sig:
            yield f"· {cname}: no change since last packet — skipped"
            continue

        course_dir = os.path.join(stu_root, safe_name(cname))
        info_dir = os.path.join(course_dir, "Info")
        os.makedirs(info_dir, exist_ok=True)

        # work samples (original formats) → Assignments/
        if "work" in sections:
            asg_dir = os.path.join(course_dir, "Assignments")
            os.makedirs(asg_dir, exist_ok=True)
            n = 0
            for s in subs:
                a = s.get("assignment") or {}
                stem = safe_name(a.get("name", "work"))
                body = (s.get("body") or "").strip()
                if body:
                    with open(os.path.join(asg_dir, stem + ".html"), "w",
                              encoding="utf-8") as f:
                        f.write(body)
                    n += 1
                url = (s.get("url") or "").strip()
                if url:
                    with open(os.path.join(asg_dir, stem + "_url.txt"), "w",
                              encoding="utf-8") as f:
                        f.write(url + "\n")
                    n += 1
                for att in (s.get("attachments") or []):
                    orig = att.get("filename") or att.get("display_name") or "file"
                    dest = os.path.join(asg_dir, stem + " - " + safe_name(orig))
                    ext = os.path.splitext(orig)[1]
                    if ext and not dest.endswith(ext):
                        dest += ext
                    try:
                        _download_binary(session, att["url"], dest)
                        n += 1
                    except Exception as e:
                        yield f"  !! {cname}/{stem}: {e}"
            yield f"✓ {cname}: {n} work file(s)"

        # Info DOCX
        blocks = _info_blocks(subs, curve_rows, sections)
        out = os.path.join(info_dir, f"{safe_name(student_name)} - {safe_name(cname)} "
                                     f"- {datetime.now():%Y-%m-%d}.docx")
        _render_info_docx(out, student_name, cname, blocks)
        yield f"✓ {cname}: Info document written"
        manifest[cid] = {"signature": sig,
                         "last_run": datetime.now().isoformat(timespec="seconds")}

    if not any_course:
        yield "· student not found in any selected course"
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    yield f"FOLDER: {stu_root}"