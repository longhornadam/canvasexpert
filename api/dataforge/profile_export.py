#!/usr/bin/env python3
"""Pseudonym-keyed standards profile, for driving grouping and differentiation.

Rolls every growth snapshot under CanvasExpert's `_System/DataForge/history/`
zone into one per-student view of which standards are weak, so another tool can
decide tiers from it.

This artifact is SAFE. It contains pseudonyms, standard codes, and scores, and
no real name or local ID. It is the half of the CanvasExpert handshake that can
travel: an assistant can reason over it, and it can sit in a synced folder.

The other half, which student a pseudonym refers to, stays in the private Identity
Vault on this machine and is never written here. Nothing in this module needs or
produces real identities.

Grain: reporting-category snapshots are excluded. An RC average and a TEKS
average are different measurements and tiering on a mix of them is meaningless.
"""

import json
from datetime import date
from pathlib import Path
from typing import Dict, List

from api.webui import workspace

from . import history_store

FORMAT = "dataforge.standards_profile.v1"
PROFILE_FILENAME = "standards-profile.json"

# Below this, a standard counts as weak enough to be worth grouping on. Scores
# in snapshots are percent correct 0-100.
DEFAULT_WEAK_BELOW = 70.0


def _usable_snapshots(paths, reporting_categories: bool = False) -> List[dict]:
    """Snapshots of one grain, oldest first.

    Learning Standard Breakdown and Individual Responses both report against
    TEKS codes, so they pool. Only Reporting Category breakdowns are a
    different grain, and they are the ones held out.
    """
    out = []
    for snap in history_store.list_snapshots(paths):
        # Snapshots written before breakdown_type existed are TEKS-grain ones,
        # since reporting-category files could not be parsed at all then.
        is_rc = (snap.get("breakdown_type") or "learning_standard") == "reporting_category"
        if is_rc != reporting_categories:
            continue
        out.append(snap)
    return out


def build_profile(paths, weak_below: float = DEFAULT_WEAK_BELOW,
                  reporting_categories: bool = False) -> dict:
    """Per-pseudonym standard mastery across every snapshot.

    Set reporting_categories=True to profile the RC grain instead. The two are
    never combined, because an RC average and a TEKS average are different
    measurements.
    """
    snapshots = _usable_snapshots(paths, reporting_categories)

    students: Dict[str, dict] = {}
    legacy_snapshots = 0

    for snap in snapshots:
        covered = snap.get("standards") or []
        if not covered:
            # Written before the standard list was recorded. Its misses are
            # still usable; its mastered standards are not recoverable.
            legacy_snapshots += 1
        label = snap.get("label") or snap.get("id")
        when = snap.get("date") or ""

        for s in snap.get("students", []):
            pseudonym = s.get("n")
            if not pseudonym:
                continue
            rec = students.setdefault(pseudonym, {
                "assessments": 0,
                "latest_pct": None,
                "latest_date": "",
                "standards": {},
            })
            rec["assessments"] += 1
            if when >= rec["latest_date"]:
                rec["latest_date"] = when
                rec["latest_pct"] = s.get("pct")

            missed = s.get("missed") or {}
            for code in covered or missed.keys():
                score = missed.get(code)
                # Absent from `missed` while present in `covered` means mastered.
                value = 100.0 if code not in missed else (0.0 if score is None else score)
                entry = rec["standards"].setdefault(code, {
                    "attempts": 0, "scores": [], "latest": None,
                    "latest_date": "", "assessed_in": [],
                })
                entry["attempts"] += 1
                entry["scores"].append(value)
                entry["assessed_in"].append(label)
                if when >= entry["latest_date"]:
                    entry["latest_date"] = when
                    entry["latest"] = value

    for rec in students.values():
        for code, entry in rec["standards"].items():
            scores = entry.pop("scores")
            entry["mean"] = round(sum(scores) / len(scores), 1) if scores else None
            entry["weak"] = entry["latest"] is not None and entry["latest"] < weak_below
        rec["weak_standards"] = sorted(
            [c for c, e in rec["standards"].items() if e["weak"]],
            key=lambda c: rec["standards"][c]["latest"],
        )

    return {
        "format": FORMAT,
        "generated": date.today().isoformat(),
        "grain": "reporting_category" if reporting_categories else "learning_standard",
        "weak_below": weak_below,
        "snapshots_used": len(snapshots),
        "snapshots_without_standard_list": legacy_snapshots,
        "student_count": len(students),
        "note": (
            "Pseudonyms only, no real names or IDs. Scores are percent correct "
            "(0-100). A standard is listed for a student only if the assessment "
            "covered it. Resolve a pseudonym to a Canvas student locally via "
            "the Identity Vault; that mapping is never included here."
        ),
        "students": students,
    }


class SharedPublishError(RuntimeError):
    """Raised when the standards profile fails its safety check."""


def publish_profile(paths, anonymizer=None, weak_below: float = DEFAULT_WEAK_BELOW) -> Path:
    """Write the standards profile into CanvasExpert's AI workspace zone.

    The profile is re-scanned against the anonymizer immediately before it is
    written. It is built from pseudonym-only snapshots and should never contain
    a real identity, so a hit here means a bug on this side, never something
    for the teacher to clean up by hand. Refuse rather than publish.
    """
    target_dir = Path(workspace.for_ai_root()) / "DataForge"

    profile = build_profile(paths, weak_below=weak_below)
    profile["grouping"] = group_by_standard(profile)
    blob = json.dumps(profile, indent=2, ensure_ascii=False)

    if anonymizer is not None:
        leaks = anonymizer.detect_leaks(blob)
        if leaks:
            raise SharedPublishError(
                "Refusing to publish the standards profile: it still contains "
                f"{len(leaks)} real identity value(s). This is a DataForge bug, "
                "not something to fix by editing the file."
            )

    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / PROFILE_FILENAME
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(blob, encoding="utf-8")
    tmp.replace(target)
    return target


def group_by_standard(profile: dict) -> Dict[str, List[str]]:
    """standard code -> pseudonyms currently weak on it.

    The shape grouping actually wants: who needs reteaching on what. Pair it
    with a crosswalk to turn each list into Canvas group membership.
    """
    out: Dict[str, List[str]] = {}
    for pseudonym, rec in profile.get("students", {}).items():
        for code in rec.get("weak_standards", []):
            out.setdefault(code, []).append(pseudonym)
    return {k: sorted(v) for k, v in sorted(out.items(), key=lambda kv: -len(kv[1]))}
