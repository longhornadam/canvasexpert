"""Parse academic-calendar CSVs for Canvas Expert.

Pure stdlib — no FastAPI or app imports. Called by routes/calendar.py and
potentially by the gradebook sweep.

_parse_calendar_csv(content: str) -> (sorted_dates: list[str], grading_periods: list[dict], events: list[dict])
"""


def _parse_calendar_csv(content: str) -> tuple:
    """Parse a calendar CSV. Auto-detects two formats:

    Canonical (PISD 7-col): school_year,row_type,code,name,start_date,end_date,...
      - row_type "Holiday" / "No School for Students" / "Holiday for Students/Teachers"
        → no-count dates (every calendar day in range)
      - row_type "Academic Period" → grading period preset

    Simple (custom 4-col): Category,Name,Start Date,End Date
      - Category "Student Day Off" / "No School" → no-count dates
      - Category "Academic Period" → grading period preset

    Returns (sorted_dates, grading_periods, events).  Events are public
    calendar facts for classroom displays; they contain no source path or district config.
      - sorted_dates:    [YYYY-MM-DD]
      - grading_periods: [{name, code, start, end}]
    Accepts YYYY-MM-DD or MM/DD/YYYY date formats.
    """
    import csv as _csv
    import io as _io
    import re as _re
    from datetime import date as _date, timedelta as _td

    _NO_SCHOOL_TYPES = {"holiday", "no school for students",
                        "holiday for students/teachers"}

    def _pd(s):
        s = s.strip()
        try:
            return _date.fromisoformat(s)
        except ValueError:
            pass
        parts = s.split("/")
        if len(parts) == 3:
            try:
                return _date(int(parts[2]), int(parts[0]), int(parts[1]))
            except ValueError as exc:
                from api import operational_log
                operational_log.emit("school_calendar.row_parse", "failed", error_class=type(exc))
        return None

    def _expand(d_start, d_end, out: set):
        d = d_start
        while d <= d_end:
            out.add(d.isoformat())
            d += _td(days=1)

    def _derive_code(name: str, used: set) -> str:
        """Deterministic uppercase alphanumeric/underscore slug from a Simple-
        format period's name, for a source row that carries no code column.
        Collisions resolve with _2, _3, ... in source order."""
        slug = _re.sub(r"[^A-Z0-9]+", "_", (name or "").strip().upper()).strip("_")
        if not slug:
            slug = "PERIOD"
        candidate = slug
        suffix = 2
        while candidate in used:
            candidate = f"{slug}_{suffix}"
            suffix += 1
        used.add(candidate)
        return candidate

    dates: set = set()
    periods: list = []
    events: list = []
    used_codes: set = set()
    reader = _csv.DictReader(_io.StringIO(content))
    fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]
    canonical = "row_type" in fieldnames and "start_date" in fieldnames

    for row in reader:
        if canonical:
            row_type = (row.get("row_type") or "").strip().lower()
            code     = (row.get("code")     or "").strip()
            name     = (row.get("name")     or "").strip()
            start_s  = (row.get("start_date") or "").strip()
            end_s    = (row.get("end_date")   or "").strip()
            report_s = (row.get("report_issue_date") or "").strip()
        else:
            row_type = (row.get("Category") or "").strip().lower()
            code     = ""
            name     = (row.get("Name")      or "").strip()
            start_s  = (row.get("Start Date") or "").strip()
            end_s    = (row.get("End Date")   or "").strip()
            report_s = ""

        if not start_s or not end_s:
            continue
        d_start = _pd(start_s)
        d_end   = _pd(end_s)
        if not d_start or not d_end:
            continue

        if canonical:
            if row_type in _NO_SCHOOL_TYPES:
                _expand(d_start, d_end, dates)
                events.append({"kind": "no_school", "label": name or "No school",
                               "start": d_start.isoformat(), "end": d_end.isoformat(),
                               "source_subtype": row_type})
            elif row_type == "academic period":
                period = {"name": name, "code": code,
                                "start": d_start.isoformat(),
                                "end":   d_end.isoformat()}
                periods.append(period)
                events.append({"kind": "grading_period_end", "label": name or code,
                               "code": code, "end": d_end.isoformat()})
                report = _pd(report_s) if report_s else None
                if report:
                    events.append({"kind": "report_card", "label": name or code,
                                   "code": code, "report_issue_date": report.isoformat()})
        else:
            if "day off" in row_type or "no school" in row_type:
                _expand(d_start, d_end, dates)
                events.append({"kind": "no_school", "label": name or "No school",
                               "start": d_start.isoformat(), "end": d_end.isoformat(),
                               "source_subtype": row_type})
            elif "academic period" in row_type:
                if not code:
                    code = _derive_code(name, used_codes)
                period = {"name": name, "code": code,
                                "start": d_start.isoformat(),
                                "end":   d_end.isoformat()}
                periods.append(period)
                events.append({"kind": "grading_period_end", "label": name or code,
                               "code": code, "end": d_end.isoformat()})

    return sorted(dates), periods, events
