"""Calendar page and APIs -- the canonical School Calendar surface.

One primary-nav working page plus the routes that back it: readiness/upcoming
projection, complete-year create (optionally seeded from a parsed academic
CSV), and the shared preview/apply day-change operation the UI and MCP both
call through api/webui/school_calendar.py.

Routes: GET  /calendar
        GET  /api/calendar
        POST /api/calendar/create
        POST /api/calendar/import
        GET  /api/calendar/import/template
        POST /api/calendar/change/preview
        POST /api/calendar/change/apply
"""
import json
import os
from datetime import date, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from .. import calendar_csv, config, deps, school_calendar, schedule_setup, workspace
from ..deps import API_DIR, templates

router = APIRouter(tags=["calendar"])

_TEMPLATE_PATH = os.path.join(API_DIR, "default_docs", "Calendars", "calendar_template.csv")

# How far past today the Calendar page's first screenful looks for upcoming
# dates. A separate, larger number from Panels' whats-due window -- this is a
# glance at the calendar itself, not an assignment due-date projection.
UPCOMING_LOOKAHEAD_DAYS = 14


@router.get("/calendar")
def calendar_page(request: Request):
    return templates.TemplateResponse(request, "calendar.html", {"nav_section": "calendar"})


def _bell_schedule_summary() -> dict:
    bell_schedules, bell_problems = deps.load_bell_schedules()
    found = [
        {"name": entry["name"], "label": entry["label"], "schedule_id": entry["schedule_id"],
         "period_count": len(bell_schedules.get(entry["schedule_id"], []))}
        for entry in deps.list_bell_schedule_files()
    ]
    return {"found": found, "problems": schedule_setup.real_problems(bell_problems)}


@router.get("/api/calendar")
def get_calendar():
    bell_schedules, _bell_problems = deps.load_bell_schedules()
    calendar_readiness = school_calendar.readiness(bell_schedule_ids=bell_schedules)
    teacher_blocks, teacher_problems = schedule_setup.load_blocks()

    upcoming = {}
    if calendar_readiness.get("status") != "unconfigured":
        today = date.today()
        horizon = today + timedelta(days=UPCOMING_LOOKAHEAD_DAYS)
        projection, _problems = school_calendar.range_projection(
            today.isoformat(), horizon.isoformat())
        upcoming = projection or {}

    return JSONResponse({
        "ok": True,
        "readiness": calendar_readiness,
        "bell_schedules": _bell_schedule_summary(),
        "teacher_schedule": {
            "blocks": teacher_blocks,
            "problems": schedule_setup.real_problems(teacher_problems),
            "path": schedule_setup.teacher_schedule_path(),
        },
        "courses": [
            {"id": str(course["id"]), "name": config.course_display_name(course["id"]),
             "active": bool(course.get("active", True))}
            for course in config.saved_courses()
        ],
        "upcoming": upcoming,
        "folders": {
            "calendars": workspace.library_folder("Calendars"),
            "smartdecks": workspace.library_folder("SmartDecks"),
        },
    })


@router.post("/api/calendar/create")
def create_calendar(
    school_year: str = Form(...),
    coverage_start: str = Form(...),
    coverage_end: str = Form(...),
    default_schedule_id: str = Form(...),
    weekday_schedules: str = Form(default="{}"),
    no_school_dates: str = Form(default="[]"),
    no_regular_classes_dates: str = Form(default="[]"),
    date_labels: str = Form(default="{}"),
    grading_periods: str = Form(default="[]"),
):
    try:
        weekday_map = json.loads(weekday_schedules)
        no_school = json.loads(no_school_dates)
        no_regular = json.loads(no_regular_classes_dates)
        labels = json.loads(date_labels)
        periods = json.loads(grading_periods)
    except json.JSONDecodeError as exc:
        return JSONResponse({"ok": False, "problems": [f"bad request: {exc}"]})

    doc, problems = school_calendar.create_school_year(
        school_year=school_year, coverage_start=coverage_start, coverage_end=coverage_end,
        default_schedule_id=default_schedule_id, weekday_schedules=weekday_map,
        no_school_dates=no_school, no_regular_classes_dates=no_regular,
        date_labels=labels, grading_periods=periods,
    )
    if problems or doc is None:
        return JSONResponse({"ok": False, "problems": problems})
    return JSONResponse({
        "ok": True,
        "revision": doc["revision"],
        "school_year": doc["school_year"],
        "coverage": doc["coverage"],
        "day_count": len(doc["days"]),
    })


@router.post("/api/calendar/import")
def import_academic_csv(content: str = Form(...)):
    """Parse an academic-calendar CSV into create() inputs for teacher review.

    Read-only: nothing is written here. The teacher reviews the parsed dates
    and periods on the Calendar page, then /api/calendar/create writes the
    complete validated document in one step.
    """
    no_school_dates, periods, events = calendar_csv._parse_calendar_csv(content)
    date_labels = {
        event["start"]: event["label"]
        for event in events
        if event.get("kind") == "no_school" and event.get("start") and event.get("label")
    }
    report_issue_by_code = {
        event["code"]: event["report_issue_date"]
        for event in events
        if event.get("kind") == "report_card" and event.get("code")
    }
    grading_periods = [
        {**period, "report_issue_date": report_issue_by_code[period["code"]]}
        if period.get("code") in report_issue_by_code else period
        for period in periods
    ]
    return JSONResponse({
        "ok": True,
        "no_school_dates": no_school_dates,
        "date_labels": date_labels,
        "grading_periods": grading_periods,
    })


@router.get("/api/calendar/import/template")
def calendar_import_template():
    """Download a blank, district-agnostic calendar CSV template for editing."""
    fname = "calendar_template.csv"
    if os.path.exists(_TEMPLATE_PATH):
        return FileResponse(_TEMPLATE_PATH, media_type="text/csv", filename=fname)
    fallback = (
        "school_year,row_type,code,name,start_date,end_date,report_issue_date,basis\n"
        "YYYY-YY,Academic Period,T1,Term 1 / Report Card 1,YYYY-MM-DD,YYYY-MM-DD,YYYY-MM-DD,\n"
        "YYYY-YY,Academic Period,T2,Term 2 / Report Card 2,YYYY-MM-DD,YYYY-MM-DD,YYYY-MM-DD,\n"
        "YYYY-YY,Academic Period,T3,Term 3 / Report Card 3,YYYY-MM-DD,YYYY-MM-DD,YYYY-MM-DD,\n"
        "YYYY-YY,Academic Period,T4,Term 4 / Report Card 4,YYYY-MM-DD,YYYY-MM-DD,YYYY-MM-DD,\n"
        "YYYY-YY,Holiday,,Labor Day,YYYY-MM-DD,YYYY-MM-DD,,\n"
        "YYYY-YY,Holiday,,Thanksgiving Break,YYYY-MM-DD,YYYY-MM-DD,,\n"
        "YYYY-YY,Holiday,,Christmas Break,YYYY-MM-DD,YYYY-MM-DD,,\n"
        "YYYY-YY,Holiday,,MLK Jr. Day,YYYY-MM-DD,YYYY-MM-DD,,\n"
        "YYYY-YY,Holiday,,Spring Break,YYYY-MM-DD,YYYY-MM-DD,,\n"
        "YYYY-YY,Holiday,,Easter Break,YYYY-MM-DD,YYYY-MM-DD,,\n"
        "YYYY-YY,Holiday,,Memorial Day,YYYY-MM-DD,YYYY-MM-DD,,\n"
    )
    return Response(fallback, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.post("/api/calendar/change/preview")
def preview_calendar_change(
    kind: str = Form(...),
    schedule_id: str = Form(default=""),
    label: str = Form(default=""),
    dates: str = Form(default=""),
    date_from: str = Form(default=""),
    date_to: str = Form(default=""),
    weekdays: str = Form(default=""),
):
    try:
        dates_list = json.loads(dates) if dates else None
        weekdays_list = json.loads(weekdays) if weekdays else None
    except json.JSONDecodeError as exc:
        return JSONResponse({"ok": False, "problems": [f"bad request: {exc}"]})

    preview, problems = school_calendar.preview_change(
        kind=kind, schedule_id=(schedule_id or None), label=(label or None),
        dates=dates_list, date_from=(date_from or None), date_to=(date_to or None),
        weekdays=weekdays_list,
    )
    if problems or preview is None:
        return JSONResponse({"ok": False, "problems": problems})
    return JSONResponse({"ok": True, **preview})


@router.post("/api/calendar/change/apply")
def apply_calendar_change(expected_revision: int = Form(...), preview: str = Form(...)):
    try:
        preview_payload = json.loads(preview)
    except json.JSONDecodeError as exc:
        return JSONResponse({"ok": False, "problems": [f"bad request: {exc}"]})

    doc, problems = school_calendar.apply_change(
        preview_payload, expected_revision=expected_revision)
    if problems or doc is None:
        return JSONResponse({"ok": False, "problems": problems})
    return JSONResponse({"ok": True, "revision": doc["revision"]})
