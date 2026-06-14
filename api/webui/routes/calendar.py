"""Calendar API routes for Canvas Expert.

One APIRouter; 5 routes for managing the academic calendar used by the
gradebook sweep (no-count dates, grading periods).

Routes: GET  /api/calendar
        POST /api/calendar/load-builtin
        POST /api/calendar/set
        GET  /api/calendar/template
        POST /api/calendar/clear
"""
import json
import os

from fastapi import APIRouter, Form
from fastapi.responses import FileResponse, JSONResponse, Response

from .. import config
from ..calendar_csv import _parse_calendar_csv
from ..deps import PISD_CALENDAR_PATHS, _PISD_LABELS

router = APIRouter(tags=["calendar"])


@router.get("/api/calendar")
def get_calendar():
    return JSONResponse({"ok": True, "calendars": config.get_calendars()})


@router.post("/api/calendar/load-builtin")
def load_builtin_calendar(year: str = Form(default="2026_27")):
    path  = PISD_CALENDAR_PATHS.get(year, PISD_CALENDAR_PATHS["2026_27"])
    key   = f"sample_isd_{year}"
    label = _PISD_LABELS.get(year, f"sample ISD {year.replace('_', '-')}")
    if not os.path.exists(path):
        return JSONResponse({"ok": False, "error": f"Built-in calendar not found for {year}."})
    with open(path, encoding="utf-8") as f:
        content = f.read()
    dates, periods = _parse_calendar_csv(content)
    config.set_calendar(key, label, dates, periods)
    return JSONResponse({"ok": True, "key": key, "label": label,
                         "count": len(dates), "grading_periods": periods})


@router.post("/api/calendar/set")
def set_calendar_route(source: str = Form(...), dates: str = Form(...),
                       grading_periods: str = Form(default="[]")):
    try:
        date_list = json.loads(dates)
        periods   = json.loads(grading_periods)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})
    config.set_calendar("custom", source or "Custom", date_list, periods)
    return JSONResponse({"ok": True})


@router.get("/api/calendar/template")
def calendar_template(year: str = "2026_27"):
    """Download a PISD calendar CSV as a template for editing to a new year."""
    path  = PISD_CALENDAR_PATHS.get(year, PISD_CALENDAR_PATHS["2026_27"])
    fname = f"calendar_template_{year}.csv"
    if os.path.exists(path):
        return FileResponse(path, media_type="text/csv", filename=fname)
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


@router.post("/api/calendar/clear")
def clear_calendar(source: str = Form(default="")):
    if source:
        config.remove_calendar(source)
    else:
        config.clear_all_calendars()
    return JSONResponse({"ok": True})