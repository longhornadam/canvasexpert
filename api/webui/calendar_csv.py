"""Parse academic-calendar CSVs for Canvas Expert.

Pure stdlib — no FastAPI or app imports. Called by routes/calendar.py and
potentially by the gradebook sweep.

_parse_calendar_csv(content: str) -> (sorted_dates: list[str], grading_periods: list[dict], events: list[dict], notes: list[str])
"""


def _parse_calendar_csv(content: str) -> tuple:
    """Parse a calendar CSV. Auto-detects two formats:

    Canonical (8-col): school_year,row_type,code,name,start_date,end_date,report_issue_date,basis
      - row_type "Holiday" / "No School for Students" / "Holiday for Students/Teachers"
        → no-count dates (every calendar day in range)
      - row_type "Academic Period" → grading period preset.  An empty code cell
        falls back to the same derived slug the Simple format uses.

    Simple (custom 4-col): Category,Name,Start Date,End Date
      - Category "Holiday" / "Student Day Off" / "No School" → no-count dates
      - Category "Academic Period" → grading period preset

    Header cells are matched with case and surrounding whitespace folded away,
    so " Row_Type " reads as row_type and "start date" as "Start Date".  The
    spellings above stay the advertised ones; this is tolerance for near-misses,
    not a third format.

    Returns (sorted_dates, grading_periods, events, notes).  Events are public
    calendar facts for classroom displays; they contain no source path or district config.
      - sorted_dates:    [YYYY-MM-DD]
      - grading_periods: [{name, code, start, end}]
      - notes:           ["row 4: skipped, ...", ...] — one short line per row
        whose data could not be used, so a teacher can see why it did not land
        instead of getting a silent success.  Empty when every row parsed.
        Row numbers count the header as row 1, matching the source spreadsheet.
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

    def _cells(row: dict) -> dict:
        """Re-key one source row so lookups can use the documented spelling.

        Format detection folds case and padding out of the header, so reading
        values back under the raw header text is what turned a
        "Row_Type,...,Start_Date" file into rows of empty strings: detected as
        canonical, then every field missed. Folding both sides the same way
        retires that whole class of near-miss. Non-string keys are DictReader's
        overflow bucket for unnamed extra columns — nothing we read lives there.
        """
        folded = {}
        for key, value in row.items():
            if not isinstance(key, str):
                continue
            folded[key.strip().lower()] = value if isinstance(value, str) else ""
        return folded

    def _derive_code(name: str, used: set) -> str:
        """Deterministic uppercase alphanumeric/underscore slug from a period's
        name, for a source row that carries no code.
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

    def _claim_code(code: str, name: str, used: set) -> str:
        """Settle one period's code and reserve it against later rows.

        A code the source supplied is authoritative and travels verbatim; only
        an empty cell derives a slug. Reserving the supplied ones too is what
        stops a later derived slug from landing on a code already in use, which
        would silently merge two grading periods downstream.
        """
        if code:
            used.add(code.upper())
            return code
        return _derive_code(name, used)

    def _unusable(row_num: int, column: str, value: str) -> str:
        """One note line for a row whose type cell names nothing we handle."""
        if not value:
            return f"row {row_num}: skipped, no {column} given"
        return f"row {row_num}: skipped, unrecognized {column} {value!r}"

    dates: set = set()
    periods: list = []
    events: list = []
    notes: list = []
    used_codes: set = set()
    reader = _csv.DictReader(_io.StringIO(content))
    fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]
    canonical = "row_type" in fieldnames and "start_date" in fieldnames
    type_column = "row_type" if canonical else "Category"

    for row in reader:
        # DictReader counts physical lines, so the header is row 1 and this is
        # the row number the teacher sees in their own spreadsheet.
        row_num = reader.line_num
        cells = _cells(row)
        if canonical:
            type_raw = cells.get("row_type", "").strip()
            code     = cells.get("code",     "").strip()
            name     = cells.get("name",     "").strip()
            start_s  = cells.get("start_date", "").strip()
            end_s    = cells.get("end_date",   "").strip()
            report_s = cells.get("report_issue_date", "").strip()
        else:
            type_raw = cells.get("category", "").strip()
            code     = ""
            name     = cells.get("name",       "").strip()
            start_s  = cells.get("start date", "").strip()
            end_s    = cells.get("end date",   "").strip()
            report_s = ""
        row_type = type_raw.lower()

        # A row of nothing but commas is spreadsheet filler, not lost data;
        # noting it would only bury the rows that actually went missing.
        if not any(value.strip() for value in cells.values()):
            continue

        if not start_s or not end_s:
            missing = ("start and end date" if not start_s and not end_s
                       else "start date" if not start_s else "end date")
            notes.append(f"row {row_num}: skipped, missing {missing}")
            continue
        d_start = _pd(start_s)
        d_end   = _pd(end_s)
        if not d_start or not d_end:
            notes.append(f"row {row_num}: skipped, unreadable date "
                         f"{(start_s if not d_start else end_s)!r}")
            continue

        if canonical:
            if row_type in _NO_SCHOOL_TYPES:
                _expand(d_start, d_end, dates)
                events.append({"kind": "no_school", "label": name or "No school",
                               "start": d_start.isoformat(), "end": d_end.isoformat(),
                               "source_subtype": row_type})
            elif row_type == "academic period":
                code = _claim_code(code, name, used_codes)
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
                elif report_s:
                    notes.append(f"row {row_num}: kept, but report card date "
                                 f"{report_s!r} was unreadable")
            else:
                notes.append(_unusable(row_num, type_column, type_raw))
        else:
            if "holiday" in row_type or "day off" in row_type or "no school" in row_type:
                _expand(d_start, d_end, dates)
                events.append({"kind": "no_school", "label": name or "No school",
                               "start": d_start.isoformat(), "end": d_end.isoformat(),
                               "source_subtype": row_type})
            elif "academic period" in row_type:
                code = _claim_code(code, name, used_codes)
                period = {"name": name, "code": code,
                                "start": d_start.isoformat(),
                                "end":   d_end.isoformat()}
                periods.append(period)
                events.append({"kind": "grading_period_end", "label": name or code,
                               "code": code, "end": d_end.isoformat()})
            else:
                notes.append(_unusable(row_num, type_column, type_raw))

    return sorted(dates), periods, events, notes
