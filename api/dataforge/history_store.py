#!/usr/bin/env python3
"""
Longitudinal snapshot store for tier-movement tracking.

Each processed assessment is saved as one compact JSON snapshot under the
CanvasExpert `_System/DataForge/history/` zone. Students are identified ONLY by
their stable pseudonym (e.g. Student_001), which the local anonymize map keeps
consistent across assessments — so a student can be followed Fall → Spring
without storing any real name. Snapshots therefore only make sense for
anonymized (de-identified) runs, and we refuse to save anything else.

Chronology is driven by an editable `date` field (defaults to processing day),
so a teacher can batch-process old + new files and still order them correctly.
"""

import json
import re
from datetime import date, datetime
from pathlib import Path


def _history_dir(paths) -> Path:
    d = paths.history_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(label: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", label).strip("-").lower()
    return s or "assessment"


def save_snapshot(paths, result: dict) -> str:
    """Persist one assessment result as a longitudinal snapshot.

    Keyed by a slug of the assessment label, so re-processing the same
    assessment updates its snapshot in place. A previously teacher-edited
    `date` is preserved across re-processing.
    """
    # Key by the unique descriptive name (includes campus) so two campuses
    # sitting the same-named assessment don't collide into one snapshot.
    descriptive = result.get("descriptive") or result.get("assessment_name") or "assessment"
    label = result.get("assessment_name") or descriptive
    snap_id = _slug(descriptive)
    path = _history_dir(paths) / f"{snap_id}.json"

    existing_date = None
    if path.exists():
        try:
            existing_date = json.loads(path.read_text(encoding="utf-8")).get("date")
        except Exception:
            existing_date = None

    # The leading number of the descriptive ("45 ...", "67 ...") is the campus
    # code the teacher recognizes — a concise disambiguator for the UI.
    m = re.match(r"^\s*(\d{1,3})\b", descriptive)
    campus_code = m.group(1) if m else ""

    snapshot = {
        "id": snap_id,
        "label": label,
        "campus_code": campus_code,
        "grade": result.get("grade"),
        "type": result.get("type"),
        # Which grain this snapshot is. Reporting categories and learning
        # standards are not comparable, so anything rolling snapshots up has to
        # keep them apart.
        "breakdown_type": result.get("breakdown_type"),
        # Every standard this assessment covered. Students carry only the ones
        # they missed, so without this list there is no way to tell a standard
        # a student mastered from one they were never assessed on.
        "standards": [s.get("code") for s in result.get("standards", []) if s.get("code")],
        "date": existing_date or date.today().isoformat(),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "students": [
            {
                "n": s["n"],
                "pct": s["pct"],
                "app": s.get("app"),
                "met": s.get("met"),
                "mas": s.get("mas"),
                "missed": s.get("missed", {}),
            }
            for s in result.get("tier_students", [])
        ],
    }
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=0), encoding="utf-8")
    return snap_id


def list_snapshots(paths) -> list:
    """Return all snapshots, chronological by (date, saved_at)."""
    out = []
    for p in _history_dir(paths).glob("*.json"):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    out.sort(key=lambda s: (s.get("date", ""), s.get("saved_at", "")))
    return out


def update_date(paths, snap_id: str, new_date: str) -> bool:
    path = _history_dir(paths) / f"{_slug(snap_id)}.json"
    if not path.exists():
        return False
    # Validate YYYY-MM-DD.
    try:
        datetime.strptime(new_date, "%Y-%m-%d")
    except ValueError:
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    data["date"] = new_date
    path.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    return True


def delete_snapshot(paths, snap_id: str) -> bool:
    path = _history_dir(paths) / f"{_slug(snap_id)}.json"
    if path.exists():
        path.unlink()
        return True
    return False
