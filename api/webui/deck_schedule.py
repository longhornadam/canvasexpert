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
    """CSV text -> ([{period_id, start, end}], problems).

    Columns: period_id,start,end (header row required).
    start/end are 24h "HH:MM" local wall-clock strings. No timezone math.

    Returns (periods_list, problems_list):
    - periods_list: [{period_id, start, end}, ...]
    - problems_list: human-readable issue strings (empty if no problems)
    """
    import csv as _csv
    import io as _io

    periods = []
    problems = []
    seen_ids = {}

    reader = _csv.DictReader(_io.StringIO(content))
    if not reader.fieldnames:
        return periods, problems

    fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]
    if "period_id" not in fieldnames or "start" not in fieldnames or "end" not in fieldnames:
        return periods, problems

    for row in reader:
        period_id = (row.get("period_id") or "").strip()
        start = (row.get("start") or "").strip()
        end = (row.get("end") or "").strip()

        if not period_id or not start or not end:
            continue

        entry = {"period_id": period_id, "start": start, "end": end}

        # Validate time format (HH:MM)
        for time_val in [start, end]:
            if not _is_valid_time(time_val):
                problems.append(f"Invalid time format in period {period_id}: {time_val}")

        # Check if end is before start (but keep the row anyway)
        if _is_valid_time(start) and _is_valid_time(end) and start > end:
            problems.append(
                f"Period {period_id}: end time {end} is before start time {start}"
            )

        # Track duplicates (last one wins)
        if period_id in seen_ids:
            problems.append(f"Duplicate period_id {period_id}; using the last row")
            periods[seen_ids[period_id]] = entry
        else:
            seen_ids[period_id] = len(periods)
            periods.append(entry)

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
     "blocks": [{"name": "4th/5th", "raw_periods": [4, 5], "label": "ELA 7", "course_id": "9000001", "weekdays": [0, 2]}, ...]}

    raw_periods is ordered and may span multiple bell periods. label and weekdays are optional.
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


def _weekday_set(block, name) -> tuple[set | None, list]:
    """Return a block's weekday restriction and any malformed-field problem."""
    if "weekdays" not in block:
        return None, []

    weekdays = block.get("weekdays")
    if (
        not isinstance(weekdays, list)
        or any(
            isinstance(day, bool)
            or not isinstance(day, int)
            or day < 0
            or day > 6
            for day in weekdays
        )
    ):
        return None, [
            f"block '{name}': weekdays must be a list of numbers, "
            "0 for Monday through 6 for Sunday"
        ]

    return set(weekdays), []


def _block_meets(block, name, weekday) -> tuple[bool, list]:
    """Return whether a block applies today, failing open on bad input."""
    weekdays, problems = _weekday_set(block, name)
    if weekday is None or weekdays is None:
        return True, problems
    return weekday in weekdays, problems


def effective_weekdays(block) -> set:
    """Return the weekdays a block applies to, with absent or bad values unrestricted."""
    if not isinstance(block, dict):
        return set(range(7))
    weekdays, _ = _weekday_set(block, block.get("name") or "")
    return set(range(7)) if weekdays is None else weekdays


def validate_teacher_schedule(data: dict) -> list:
    """Validate the teacher schedule shape for a write operation."""
    if not isinstance(data, dict):
        return ["teacher schedule must be a dict"]

    blocks = data.get("blocks")
    if not isinstance(blocks, list):
        return ["blocks must be a list"]

    problems = []
    named_blocks = []
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

        weekdays, weekday_problems = _weekday_set(block, display_name)
        problems.extend(weekday_problems)

        if "label" in block and not isinstance(block.get("label"), str):
            problems.append(f"block '{display_name}': label must be a string")

        if "course_id" in block and not isinstance(block.get("course_id"), str):
            problems.append(f"block '{display_name}' course_id must be a string")

        if valid_name:
            named_blocks.append((name, set(range(7)) if weekdays is None else weekdays))

    for index, (name, weekdays) in enumerate(named_blocks):
        for other_name, other_weekdays in named_blocks[:index]:
            if name == other_name and weekdays.intersection(other_weekdays):
                problems.append(
                    f"block '{name}' is listed more than once for the same weekday; "
                    "give one a different name or narrow its weekdays"
                )
                break

    return problems


def resolve_day(date, day_calendar, bell_schedules, teacher_schedule) -> tuple:
    """Resolve a teacher's blocks for a specific date.

    date: "YYYY-MM-DD" string
    day_calendar: output of parse_day_calendar
    bell_schedules: {schedule_id: output of parse_bell_schedule}
    teacher_schedule: output of parse_teacher_schedule

    Returns (blocks_list, problems_list):
    - blocks_list: [{name, label, start, end, raw_periods, schedule_id}, ...]
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

    # Get the bell schedule for today
    periods_list = bell_schedules[schedule_id]
    period_map = {p["period_id"]: p for p in periods_list}

    parsed = _parse_date(date)
    weekday = parsed.weekday() if parsed else None

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

        meets, weekday_problems = _block_meets(block, name, weekday)
        problems.extend(weekday_problems)
        if not meets:
            continue

        # Convert raw_periods to strings for lookup
        period_ids = [str(p) for p in raw_periods]

        # Check if all periods are present in today's schedule
        missing_ids = [pid for pid in period_ids if pid not in period_map]

        if missing_ids:
            problems.append(
                f"block '{name}' omitted: periods {missing_ids} not in schedule '{schedule_id}'"
            )
        else:
            # All periods found: start = first period's start, end = last period's end
            first_period = period_map[period_ids[0]]
            last_period = period_map[period_ids[-1]]
            blocks.append({
                "name": name,
                "label": label,
                "start": first_period["start"],
                "end": last_period["end"],
                "raw_periods": raw_periods,
                "schedule_id": schedule_id,
            })

    # Sort by start time
    blocks.sort(key=lambda b: b["start"])

    seen_names = set()
    reported_names = set()
    for block in blocks:
        name = block["name"]
        if name in seen_names and name not in reported_names:
            problems.append(
                f"block '{name}' resolved twice for {date}; "
                "a deck will only use the later one in the day"
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
