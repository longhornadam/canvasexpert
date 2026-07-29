"""Read day plans out of the workspace.

Day plans live under `Library/Glass/day-plans/`, in the same folder as the bell
schedule they key against. It is teacher-visible content, so it sits where a
teacher can find and edit it.

A missing or unreadable plan is a note, never an exception. Glass has to keep
showing the clock and the day strip on a morning when nobody had time to write
a plan, so every failure here comes back as something calm to display.
"""
from __future__ import annotations

import json
import os
from datetime import date as date_type

from api.glass.schema import DayPlan, DayPlanError, parse_day_plan

GLASS_LIBRARY_FOLDER = "Glass"
DAY_PLANS_FOLDER = "day-plans"


def glass_folder() -> str | None:
    """The Library Glass folder, or None when no workspace is configured.

    The import is lazy because `api.webui.config._io` pulls in `keyring`, and
    reading a JSON file should not drag a keyring backend along with it.
    """
    from api.webui import workspace

    return workspace.library_folder(GLASS_LIBRARY_FOLDER)


def day_plans_folder() -> str | None:
    """The folder holding one JSON file per planned date."""
    base = glass_folder()
    return os.path.join(base, DAY_PLANS_FOLDER) if base else None


def day_plan_path(on: date_type) -> str | None:
    """Where the plan for one date lives. The date is the file name."""
    folder = day_plans_folder()
    return os.path.join(folder, f"{on.isoformat()}.json") if folder else None


def load_day_plan(on: date_type) -> tuple[DayPlan | None, list[str]]:
    """The plan for one date, plus anything worth telling the teacher."""
    path = day_plan_path(on)
    if not path:
        return None, [
            "No workspace folder is set up yet, so there is no day plan to read."
        ]
    if not os.path.isfile(path):
        return None, [
            f"No plan written for {on.isoformat()}, so the focus area stays empty."
        ]
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as err:
        return None, [
            f"{os.path.basename(path)} could not be opened: {err.strerror or err}"
        ]
    except ValueError as err:
        return None, [
            f"{os.path.basename(path)} is not valid JSON ({err}). A missing comma "
            f"or a stray quote is the usual cause."
        ]
    try:
        plan = parse_day_plan(data)
    except DayPlanError as err:
        return None, [f"{os.path.basename(path)}: {err}"]

    notes: list[str] = []
    if plan.date != on:
        notes.append(
            f"{os.path.basename(path)} says its date is {plan.date.isoformat()}. "
            f"Glass goes by the file name, so rename one of the two to match."
        )
    return plan, notes


def available_plan_dates() -> list[date_type]:
    """Every date that has a plan file, oldest first.

    Only well-formed `YYYY-MM-DD.json` names count, so a stray note or a copy
    of the template sitting in the folder is ignored rather than reported.
    """
    folder = day_plans_folder()
    if not folder or not os.path.isdir(folder):
        return []
    found: list[date_type] = []
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    for name in names:
        stem, extension = os.path.splitext(name)
        if extension.lower() != ".json":
            continue
        try:
            found.append(date_type.fromisoformat(stem))
        except ValueError:
            continue
    return sorted(found)
