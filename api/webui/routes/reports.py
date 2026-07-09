"""Reports router for Canvas Expert.

Student Reports and local file operations.
"""
import json
import os
import subprocess
import sys
from datetime import datetime

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

import requests

import downloader
import nq_report
import portfolio
import portfolio_service
import student_packet
from .. import config
from ..canvas_client import _canvas_get_all, _canvas_headers
from ..deps import _sse
from ..gradebook_service import _load_curve_events

router = APIRouter(prefix="/api", tags=["reports"])


# --------------------------------------------------------------------------
# Download settings + submission downloads
# --------------------------------------------------------------------------

@router.get("/download-root")
def get_download_root():
    return JSONResponse({"root": config.get_download_root()})


@router.get("/assignments-full")
def list_assignments_full(course_id: str):
    """All assignments for a course — used by the download picker.
    Returns id, name, submission_types, due_at, points_possible.
    """
    hdrs, base = _canvas_headers()
    if not hdrs:
        return JSONResponse({"ok": False, "error": "No token saved."})
    results, params = [], {"per_page": 100}
    url = f"{base}/api/v1/courses/{course_id}/assignments"
    while url:
        try:
            r = requests.get(url, headers=hdrs, params=params, timeout=20)
        except requests.RequestException as e:
            return JSONResponse({"ok": False, "error": str(e)})
        if r.status_code != 200:
            return JSONResponse({"ok": False, "error": f"HTTP {r.status_code}"})
        results.extend(r.json())
        params = {}
        url = None
        for part in r.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break
    assignments = [
        {
            "id":               str(a["id"]),
            "name":             a.get("name", ""),
            "submission_types": a.get("submission_types") or [],
            "due_at":           (a.get("due_at") or "")[:10],
            "points_possible":  a.get("points_possible"),
        }
        for a in results
    ]
    DL = downloader.DOWNLOADABLE_TYPES
    assignments.sort(
        key=lambda a: a["due_at"] if a["due_at"] else "0000-00-00",
        reverse=True,
    )
    assignments.sort(
        key=lambda a: 0 if set(a["submission_types"]) & DL else 1,
    )
    return JSONResponse({"ok": True, "assignments": assignments})


@router.get("/course-folder")
def course_folder(course_name: str):
    """Return the local download folder path for a course and whether it exists."""
    root = config.get_download_root()
    path = os.path.join(root, downloader.safe_name(course_name))
    return JSONResponse({"path": path, "exists": os.path.isdir(path)})


@router.get("/submissions/download/stream")
def submissions_download_stream(course_id: str, course_name: str,
                                 assignment_ids: str):
    """SSE stream — downloads submissions, yields progress lines.
    assignment_ids: comma-separated list of assignment IDs.
    Final SSE line: COURSE_FOLDER: <path>
    """
    token = config.get_token()
    if not token:
        return StreamingResponse(
            _sse(["!! No Canvas token saved.", "[exit 1]"]),
            media_type="text/event-stream",
        )
    ids  = [i.strip() for i in assignment_ids.split(",") if i.strip()]
    base = config.get_canvas_base()
    root = config.get_download_root()

    def lines():
        try:
            yield from downloader.run_download(
                course_id, course_name, ids, base, token, root
            )
            yield "[exit 0]"
        except Exception as e:
            yield f"!! Fatal: {e}"
            yield "[exit 1]"

    return StreamingResponse(_sse(lines()), media_type="text/event-stream")


# --------------------------------------------------------------------------
# Student Reports
# --------------------------------------------------------------------------

@router.get("/students")
def api_students(course_id: str):
    """Roster for one course, annotated with the machine-local monitored flag."""
    users, err = _canvas_get_all(f"/api/v1/courses/{course_id}/users",
                                 {"enrollment_type[]": "student", "per_page": 100})
    if err:
        return JSONResponse({"ok": False, "error": err})
    mon = config.get_monitored_students()
    out = [{"id": str(u["id"]),
            "name": u.get("sortable_name") or u.get("name", ""),
            "monitored": str(u["id"]) in mon} for u in (users or [])]
    out.sort(key=lambda s: s["name"].lower())
    return JSONResponse({"ok": True, "students": out})


@router.post("/students/monitor")
def api_students_monitor(user_id: str = Form(...), name: str = Form(...),
                         monitored: str = Form(...), note: str = Form("")):
    if monitored == "true":
        config.set_monitored_student(user_id, name, note)
    else:
        config.remove_monitored_student(user_id)
    return JSONResponse({"ok": True})


@router.get("/students/monitored")
def api_students_monitored():
    mon = config.get_monitored_students()
    return JSONResponse({"ok": True, "students":
        [{"user_id": uid, "name": v["name"]} for uid, v in mon.items()]})


@router.get("/student-packet/stream")
def api_student_packet_stream(user_id: str, student_name: str,
                              sections: str = "", course_ids: str = ""):
    """SSE: build one student's packet across the given (or all active) courses."""
    secs = [s for s in sections.split(",") if s] or student_packet.SECTIONS
    if course_ids:
        want = {c.strip() for c in course_ids.split(",") if c.strip()}
        courses = [c for c in config.active_courses() if str(c["id"]) in want]
    else:
        courses = config.active_courses()
    base, token = config.get_canvas_base(), config.get_token()
    if not token:
        return StreamingResponse(_sse(["!! no token", "[exit 1]"]),
                                 media_type="text/event-stream")

    def lines():
        try:
            yield from student_packet.build_packet(
                user_id, student_name, secs,
                [{"id": c["id"], "name": c["name"]} for c in courses],
                base, token, config.get_student_reports_root(),
                _load_curve_events(), skip_unchanged=False)
            yield "[exit 0]"
        except Exception as e:
            yield f"!! {e}"
            yield "[exit 1]"

    return StreamingResponse(_sse(lines()), media_type="text/event-stream")


# --------------------------------------------------------------------------
# New Quizzes writing portfolio (from a manually-downloaded Student Analysis CSV)
# --------------------------------------------------------------------------

@router.post("/portfolio/from-nq-csv")
async def portfolio_from_nq_csv(file: UploadFile = File(...),
                                quiz_title: str = Form("")):
    """Parse an uploaded New Quizzes 'Student Analysis' CSV and render one writing
    portfolio DOCX per student into the synced Student Reports folder.

    The CSV is parsed in memory and never written to disk; only the per-student
    DOCX outputs land in the (FERPA-conscious, gitignored/synced) reports root.
    """
    title = (quiz_title or "").strip() or os.path.splitext(file.filename or "")[0] or "New Quiz"
    try:
        raw = await file.read()
        text = raw.decode("utf-8-sig", errors="replace")
        data = nq_report.parse_student_analysis(text)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"Could not read CSV: {e}"})

    students = data.get("students") or []
    if not students:
        return JSONResponse({"ok": False,
                             "error": "No student rows found — is this a New Quizzes "
                                      "Student Analysis CSV?"})

    out_dir = os.path.join(config.get_student_reports_root(),
                           downloader.safe_name(title) + " - Portfolios")
    try:
        written = portfolio.render_portfolio(data, out_dir, quiz_title=title)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"Render failed: {e}"})

    return JSONResponse({"ok": True, "folder": out_dir,
                         "count": len(written), "quiz_title": title,
                         "students": [s.get("name", "") for s in students]})


@router.post("/portfolio/merged")
async def portfolio_merged(course_id: str = Form(...),
                           cohort: str = Form("monitored"),
                           quiz_title: str = Form(""),
                           date_from: str = Form(""),
                           date_to: str = Form(""),
                           file: UploadFile = File(None)):
    """Build one merged, chronological writing portfolio per student: Assignment text
    entries + uploaded files/photos (live) plus New Quizzes responses (optional CSV,
    matched by Canvas id). Synchronous — scope to the monitored cohort for speed.
    """
    token, base = config.get_token(), config.get_canvas_base()
    if not token:
        return JSONResponse({"ok": False, "error": "No Canvas token saved."})

    course = next((c for c in config.saved_courses() if str(c["id"]) == str(course_id)),
                  {"id": course_id, "name": str(course_id)})

    if cohort == "monitored":
        students = [{"id": uid, "name": v["name"]}
                    for uid, v in config.get_monitored_students().items()]
    else:
        users, err = _canvas_get_all(f"/api/v1/courses/{course_id}/users",
                                     {"enrollment_type[]": "student", "per_page": 100})
        if err:
            return JSONResponse({"ok": False, "error": err})
        students = [{"id": str(u["id"]),
                     "name": u.get("sortable_name") or u.get("name", "")}
                    for u in (users or [])]
    if not students:
        return JSONResponse({"ok": False, "error": "No students in the selected cohort."})

    parsed_nq, title = None, (quiz_title or "").strip()
    if file is not None and file.filename:
        try:
            parsed_nq = nq_report.parse_student_analysis(
                (await file.read()).decode("utf-8-sig", errors="replace"))
        except Exception as e:
            return JSONResponse({"ok": False, "error": f"Could not read CSV: {e}"})
        if not title:
            title = os.path.splitext(file.filename)[0]

    log, folder = [], config.get_student_reports_root()
    try:
        for line in portfolio_service.build_merged_portfolios(
                course, students, parsed_nq, title, base, token, folder,
                date_from.strip() or None, date_to.strip() or None):
            if line.startswith("FOLDER: "):
                folder = line[len("FOLDER: "):]
            else:
                log.append(line)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e), "log": log})

    made = sum(1 for ln in log if ln.startswith("✓"))
    return JSONResponse({"ok": True, "folder": folder, "count": made, "log": log})


# --------------------------------------------------------------------------
# Local file operations
# --------------------------------------------------------------------------

@router.post("/open-folder")
def open_folder(path: str = Form(...)):
    """Open a local folder in Windows Explorer (local server only)."""
    path = os.path.normpath(path)
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)
    try:
        subprocess.Popen(["explorer", path])
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@router.post("/open-file")
def open_file(path: str = Form(...)):
    """Open a local file with its default app (local server only) — used by the
    Feedback tools manual lane to open a pseudonymized bundle for MagicSchool/Copilot."""
    path = os.path.normpath(path)
    if not os.path.isfile(path):
        return JSONResponse({"ok": False, "error": "File not found."})
    try:
        os.startfile(path)  # noqa: Windows-only; this app is local Windows-only
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@router.post("/pick-download-folder")
def pick_download_folder():
    """Native folder picker → set as the download root (local app only)."""
    cur = config.get_download_root() or ""
    script = (
        "import sys, tkinter as tk\n"
        "from tkinter import filedialog\n"
        "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
        "p = filedialog.askdirectory(initialdir=sys.argv[1] or None,\n"
        "                            title='Choose download location')\n"
        "sys.stdout.write(p or '')\n"
    )
    try:
        out = subprocess.run([sys.executable, "-c", script, cur],
                             capture_output=True, text=True, timeout=300)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})
    chosen = (out.stdout or "").strip()
    if not chosen:
        return JSONResponse({"ok": False, "cancelled": True})
    config.set_download_root(chosen)
    return JSONResponse({"ok": True, "root": chosen})


