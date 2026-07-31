"""Parse bell schedule, day calendar, and teacher schedule CSVs and JSON.

Pure stdlib — no FastAPI, no workspace imports, no file IO at all. Called by
deps.py and potentially by MCP tools.

Three functions parse and resolve schedule data:
- parse_bell_schedule(content: str) -> (periods, problems)
- parse_day_calendar(content: str) -> (mapping, problems)
- parse_teacher_schedule(text: str) -> (data, problems)
- resolve_day(date, day_calendar, bell_schedules, teacher_schedule) -> (blocks, problems)
"""


def parse_bell_schedule(content: str) -> tuple:
    """CSV text -> ([{seq, period_id, start, end, segment}], problems).

    Columns: period_id,start,end,label? (header row required).
    start/end are 24h "HH:MM" local wall-clock strings. No timezone math.

    Returns (meetings_list, problems_list):
    - meetings_list: ordered meetings with a zero-based ``seq`` and optional
      ``segment`` from the CSV's ``label`` column
    - problems_list: human-readable issue strings (empty if no problems)
    """
    import csv as _csv
    import io as _io

    periods = []
    problems = []
    reader = _csv.DictReader(_io.StringIO(content))
    if not reader.fieldnames:
        return periods, problems

    field_map = {
        field.strip().lower(): field
        for field in (reader.fieldnames or [])
        if isinstance(field, str)
    }
    fieldnames = set(field_map)
    if "period_id" not in fieldnames or "start" not in fieldnames or "end" not in fieldnames:
        return periods, problems

    label_field = field_map.get("label")
    for row in reader:
        period_id = (row.get(field_map["period_id"]) or "").strip()
        start = (row.get(field_map["start"]) or "").strip()
        end = (row.get(field_map["end"]) or "").strip()
        segment = (row.get(label_field) or "").strip() if label_field else ""

        if not period_id or not start or not end:
            continue

        entry = {
            "period_id": period_id,
            "start": start,
            "end": end,
            "segment": segment,
        }

        # Validate time format (HH:MM)
        for time_val in [start, end]:
            if not _is_valid_time(time_val):
                problems.append(f"Invalid time format in period {period_id}: {time_val}")

        # Check if end is before start (but keep the row anyway)
        if _is_valid_time(start) and _is_valid_time(end) and start > end:
            problems.append(
                f"Period {period_id}: end time {end} is before start time {start}"
            )

        periods.append(entry)

    periods.sort(key=lambda meeting: meeting["start"])
    periods = [
        {"seq": seq, **meeting}
        for seq, meeting in enumerate(periods)
    ]

    return periods, problems


def parse_day_calendar(content: str) -> tuple:
    """CSV text -> ({"YYYY-MM-DD": schedule_id}, problems).

    Columns: date,schedule_id (header row required).
    Accepts YYYY-MM-DD or MM/DD/YYYY on input; keys are always YYYY-MM-DD.

    Returns (mapping_dict, problems_list):
    - mapping_dict: {date_isoformat: schedule_id}
    - problems_list: human-readable issue strings
    """
    import csv as _csv
    import io as _io
    from datetime import date as _date

    mapping = {}
    problems = []

    reader = _csv.DictReader(_io.StringIO(content))
    if not reader.fieldnames:
        return mapping, problems

    fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]
    if "date" not in fieldnames or "schedule_id" not in fieldnames:
        return mapping, problems

    for row in reader:
        date_str = (row.get("date") or "").strip()
        schedule_id = (row.get("schedule_id") or "").strip()

        if not date_str or not schedule_id:
            continue

        parsed_date = _parse_date(date_str)
        if not parsed_date:
            problems.append(f"Invalid date format: {date_str}")
            continue

        mapping[parsed_date.isoformat()] = schedule_id

    return mapping, problems


def parse_teacher_schedule(text: str) -> tuple:
    """JSON text -> (data, problems).

    Shape:
    {"version": "1.0-json",
     "blocks": [{"name": "4th/5th", "raw_periods": [4, 5], "label": "ELA 7", "course_id": "9000001"}, ...]}

    raw_periods is ordered and may span multiple bell periods. label is optional.
    A legacy weekdays key is ignored.
    Top-level "_comment" key (or any unknown top-level key) is silently ignored.

    Returns (data_dict, problems_list):
    - data_dict: parsed JSON structure (empty {} if parse fails)
    - problems_list: human-readable issue strings
    """
    import json as _json

    problems = []
    try:
        data = _json.loads(text)
    except _json.JSONDecodeError as e:
        problems.append(f"invalid JSON: {e}")
        return {}, problems

    if not isinstance(data, dict):
        problems.append("JSON root must be a dict/object")
        return {}, problems

    return data, problems


def validate_teacher_schedule(data: dict) -> list:
    """Validate the teacher schedule shape for a write operation."""
    if not isinstance(data, dict):
        return ["teacher schedule must be a dict"]

    blocks = data.get("blocks")
    if not isinstance(blocks, list):
        return ["blocks must be a list"]

    problems = []
    names = set()
    period_owners = {}
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            problems.append(f"block at index {index} must be a dict")
            continue

        name = block.get("name")
        valid_name = isinstance(name, str) and bool(name.strip())
        display_name = name if isinstance(name, str) else f"at index {index}"
        if not valid_name:
            problems.append(f"block at index {index} needs a non-empty string name")

        raw_periods = block.get("raw_periods")
        valid_raw_periods = (
            isinstance(raw_periods, list)
            and bool(raw_periods)
            and all(
                (isinstance(period, int) and not isinstance(period, bool))
                or (isinstance(period, str) and bool(period.strip()))
                for period in raw_periods
            )
        )
        if not valid_raw_periods:
            problems.append(
                f"block '{display_name}' must have a non-empty list of ints "
                "or non-empty strings for raw_periods"
            )

        if "label" in block and not isinstance(block.get("label"), str):
            problems.append(f"block '{display_name}': label must be a string")

        if "course_id" in block and not isinstance(block.get("course_id"), str):
            problems.append(f"block '{display_name}' course_id must be a string")

        if valid_name:
            if name in names:
                problems.append(f"block '{name}' must be unique")
            names.add(name)

        if valid_raw_periods:
            for period in raw_periods:
                period_id = str(period)
                owner = period_owners.get(period_id)
                if owner is not None and owner[0] != index:
                    problems.append(
                        f"period '{period_id}' is claimed by both blocks "
                        f"'{owner[1]}' and '{display_name}'"
                    )
                else:
                    period_owners[period_id] = (index, display_name)

    return problems


def resolve_day(date, day_calendar, bell_schedules, teacher_schedule) -> tuple:
    """Resolve a teacher's blocks for a specific date.

    date: "YYYY-MM-DD" string
    day_calendar: output of parse_day_calendar
    bell_schedules: {schedule_id: output of parse_bell_schedule}
    teacher_schedule: output of parse_teacher_schedule

    Returns (blocks_list, problems_list):
    - blocks_list: [{name, label, start, end, raw_periods, schedule_id,
      period_ids, segments, seq}, ...]
      sorted by start time
    - problems_list: human-readable issue strings
    """
    blocks = []
    problems = []

    # Look up what schedule applies today
    if date not in day_calendar:
        problems.append(f"no schedule for {date}")
        return [], problems

    schedule_id = day_calendar[date]
    if schedule_id not in bell_schedules:
        problems.append(f"schedule '{schedule_id}' not found for {date}")
        return [], problems

    # Get the ordered meetings for today. The parser has already sorted them
    # chronologically; callers supplying parsed data may also provide seq.
    periods_list = bell_schedules[schedule_id]

    # Parse teacher schedule blocks
    blocks_data = teacher_schedule.get("blocks") or []
    if not isinstance(blocks_data, list):
        problems.append("teacher_schedule blocks must be a list")
        return [], problems

    for block in blocks_data:
        if not isinstance(block, dict):
            continue

        name = block.get("name") or ""
        label = block.get("label") or ""
        raw_periods = block.get("raw_periods") or []

        if not name:
            continue

        if not isinstance(raw_periods, list) or len(raw_periods) == 0:
            problems.append(f"block '{name}' has no raw_periods")
            continue

        period_ids = [str(p) for p in raw_periods]

        runs = []
        current_run = []
        for meeting_index, meeting in enumerate(periods_list):
            if str(meeting.get("period_id")) in period_ids:
                current_run.append((meeting_index, meeting))
            elif current_run:
                runs.append(current_run)
                current_run = []
        if current_run:
            runs.append(current_run)

        for run in runs:
            first_index, first_meeting = run[0]
            last_meeting = run[-1][1]
            blocks.append({
                "name": name,
                "label": label,
                "start": first_meeting["start"],
                "end": last_meeting["end"],
                "raw_periods": raw_periods,
                "schedule_id": schedule_id,
                "period_ids": [str(meeting.get("period_id")) for _, meeting in run],
                "segments": [meeting.get("segment", "") or "" for _, meeting in run],
                "seq": first_meeting.get("seq", first_index),
            })

    # Sort by start time
    blocks.sort(key=lambda b: (b["start"], b.get("seq", 0)))

    seen_names = set()
    reported_names = set()
    for block in blocks:
        name = block["name"]
        if name in seen_names and name not in reported_names:
            problems.append(
                f"block '{name}' resolved twice for {date}; "
                "slides bind to the first meeting"
            )
            reported_names.add(name)
        seen_names.add(name)

    return blocks, problems


# ============================================================================
# Helpers
# ============================================================================

def _is_valid_time(time_str: str) -> bool:
    """Check if time is in HH:MM format (24-hour, with leading zeros)."""
    if not isinstance(time_str, str):
        return False
    parts = time_str.split(":")
    if len(parts) != 2:
        return False
    # Must have exactly 2 digits for hours and 2 digits for minutes
    if len(parts[0]) != 2 or len(parts[1]) != 2:
        return False
    try:
        h = int(parts[0])
        m = int(parts[1])
        return 0 <= h <= 23 and 0 <= m <= 59
    except ValueError:
        return False


def _parse_date(s: str):
    """Parse YYYY-MM-DD or MM/DD/YYYY; return date object or None."""
    from datetime import date as _date

    s = s.strip()
    try:
        return _date.fromisoformat(s)
    except ValueError:
        pass

    parts = s.split("/")
    if len(parts) == 3:
        try:
            return _date(int(parts[2]), int(parts[0]), int(parts[1]))
        except ValueError:
            pass

    return None
