#!/usr/bin/env python3
"""
Longitudinal snapshot store for tier-movement tracking.

Each processed assessment is saved as one compact JSON snapshot under the
CanvasExpert `_System/DataForge/history/` zone -- the same private zone that
already holds the Identity Vault. Students are identified by a stable
canvas_id, resolved through the Identity Vault at run time. A pseudonym string
is also stored on each row (`n`), but it is a point-in-time label, not the key:
a mid-year rename changes what a pseudonym-only key would mean for every
earlier row, so anything that needs a student's identity across snapshots
resolves the *current* pseudonym from the vault via canvas_id rather than
trusting the stored string. A row with no canvas_id (a prior-year student the
vault never linked, or a snapshot not yet backfilled) has only the stored
pseudonym to go on. Snapshots only make sense for anonymized (de-identified)
runs, and we refuse to save anything else.

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
                # Stable identity key, resolved from the Identity Vault at
                # processing time. Empty for a student the vault has no entry
                # for (see `VaultIdentity.canvas_id_for_student`) rather than
                # invented.
                "canvas_id": s.get("canvas_id") or "",
            }
            for s in result.get("tier_students", [])
        ],
    }
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=0), encoding="utf-8")
    return snap_id


def resolve_student_pseudonym(student: dict, identity=None) -> str:
    """The pseudonym to show for one snapshot student row, resolved fresh.

    A row that carries a canvas_id is looked up against the Identity Vault
    every time, so a mid-year rename is reflected immediately and every
    earlier snapshot keeps pointing at the same student under their new name.
    A row with no canvas_id (not yet backfilled, or a prior-year student the
    vault never linked) falls back to whatever pseudonym was stored when the
    row was written -- the best available label, not a guess.

    `identity` is a `VaultIdentity` or `None`; this function does not import
    that module, so history_store stays free of a hard dependency on it.
    """
    canvas_id = str(student.get("canvas_id") or "").strip()
    if canvas_id and identity is not None:
        resolved = identity.pseudonym_for_canvas_id(canvas_id)
        if resolved:
            return resolved
    return str(student.get("n") or "")


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
