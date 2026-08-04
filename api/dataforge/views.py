#!/usr/bin/env python3
"""
DataForge route logic, kept free of any web framework.

This module holds what each route in webui.py actually does: read
configuration, parse uploaded files, build the dashboard, walk the history
store. It imports no web framework and never touches `request`, `session`,
or any other framework global; every input a view needs arrives as an
explicit function argument.

A view returns one of the small result types below (Render, Redirect,
FileDownload, BytesDownload) or raises NotFound. webui.py is the only place
that knows how to turn those into an actual HTTP response, which is what
makes porting this package to a different host a matter of writing one new
thin shell instead of untangling this logic.
"""

import io
import json
import re
import uuid
import zipfile
from pathlib import Path

from api import operational_log

from . import canvas_join, history_store, paths as path_config, profile_export
from .identity import (
    IdentityMigrationError,
    VaultIdentity,
    backfill_canvas_ids,
    migrate_legacy_state,
    vault_path,
)
from .eduphoria_parser import (
    convert_to_json,
    create_teacher_report,
    create_parent_narratives,
    pick_parser,
)


# --- result types -------------------------------------------------------
#
# A view expresses intent with one of these; it never builds a Flask
# response directly.


class ViewError(Exception):
    """Base for view failures a host maps to an HTTP response."""


class NotFound(ViewError):
    """Maps to 404."""


class Redirect:
    """Go to a named endpoint. Host resolves the name to a URL.

    Naming the endpoint (rather than building a URL here) is what lets a
    different host resolve it its own way.
    """

    def __init__(self, endpoint: str, **params):
        self.endpoint = endpoint
        self.params = params


class Render:
    """Render a named template with a context dict."""

    def __init__(self, template: str, **context):
        self.template = template
        self.context = context


class FileDownload:
    """Send a file from disk as an attachment."""

    def __init__(self, path, download_name=None):
        self.path = path
        self.download_name = download_name


class BytesDownload:
    """Send in-memory bytes as an attachment."""

    def __init__(self, data: bytes, mimetype: str, download_name: str):
        self.data = data
        self.mimetype = mimetype
        self.download_name = download_name


# --- module-level state --------------------------------------------------
#
# In-memory store of the most recent processing run, keyed by run id.
# Local single-teacher tool, so a simple dict is fine. Cleared on restart.
# Views own this state; webui.py imports it rather than keeping its own copy.
RUNS: dict = {}


# --- helpers --------------------------------------------------------------


def _safe_filename(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]+', " ", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _error_run(paths, anonymize: bool, message: str) -> Redirect:
    """Build a run that failed before any file was processed."""
    run_id = uuid.uuid4().hex[:8]
    RUNS[run_id] = {
        "results": [],
        "errors": [{"file": "Identity Vault", "error": message}],
        "anonymized": anonymize,
        "output_dir": str(paths.output_dir),
        "snapshots_saved": 0,
    }
    return Redirect("results", run_id=run_id)


def _process_file(path: Path, identity, output_dir: Path, strip_demographics: bool) -> dict:
    """Parse one assessment file and build everything the UI needs."""
    parser, parse_source = pick_parser(path)
    data = parser.parse()
    # When anonymization is off, identity is None -> real names/IDs are emitted.
    data.metadata["_anonymizer"] = identity
    # Full de-identification also drops demographic quasi-identifiers.
    data.metadata["_strip_demographics"] = strip_demographics

    md = data.metadata
    sm = data.summary

    campus = (md.get("campus") or "").strip()
    assessment_name = (md.get("assessment_name") or "").strip()
    if campus.lower() == "exportview" or campus in assessment_name:
        campus = None
    descriptive = _safe_filename(f"{campus} {assessment_name}" if campus else assessment_name)
    if not descriptive:
        descriptive = _safe_filename(path.stem)

    json_str = convert_to_json(data)
    teacher_txt = create_teacher_report(data)
    parent_txt = create_parent_narratives(data)

    # Persist artifacts to the data folder's output dir for download/reuse.
    json_file = output_dir / f"{descriptive} - LLM Ready Results.json"
    txt_file = output_dir / f"{descriptive} - Teacher Report.txt"
    parent_file = output_dir / f"{descriptive} - Parent Narratives.txt"
    json_file.write_text(json_str, encoding="utf-8")
    txt_file.write_text(teacher_txt, encoding="utf-8")
    parent_file.write_text(parent_txt, encoding="utf-8")

    # Standards needing attention: lowest proficiency first.
    standards = []
    for a in data.standard_analysis:
        standards.append(
            {
                "code": a.standard_code,
                "canonical": a.canonical_code,
                "type": a.standard_type,
                "avg": round(a.avg_score * 100, 1),
                "proficiency": round(a.proficiency_rate, 1),
                "total": a.total_students,
            }
        )
    standards.sort(key=lambda x: x["proficiency"])

    # Minimal per-student list (using the same anonymized names as the JSON)
    # for the interactive differentiation-grouping screen. Snapshots saved
    # from a run carry each student's stable canvas_id too (never the compact
    # JSON itself -- that artifact travels further, so it stays pseudonym-only)
    # so a later mid-year rename cannot orphan their history.
    compact = json.loads(json_str)
    tier_students = [
        {
            "n": s["n"],
            "pct": s["pct"],
            "app": s.get("app"),
            "met": s.get("met"),
            "mas": s.get("mas"),
            "missed": s.get("missed", {}),
            "canvas_id": identity.canvas_id_for_student(orig.student_name, orig.local_id) if identity else "",
        }
        for s, orig in zip(compact["students"], data.students)
    ]

    return {
        "file_id": uuid.uuid4().hex[:8],
        "source_name": path.name,
        "parse_source": parse_source,
        "descriptive": descriptive,
        "demographics_stripped": strip_demographics,
        "assessment_name": md.get("assessment_name"),
        "campus": md.get("campus"),
        "grade": md.get("grade"),
        "type": md.get("assessment_type"),
        "breakdown_type": md.get("breakdown_type"),
        "total_students": sm.total_students,
        "avg_pct": round(sm.avg_percent_score * 100, 1),
        "num_standards": md.get("num_standards"),
        "approaches_pct": round(sm.approaches_percent, 1),
        "meets_pct": round(sm.meets_percent, 1),
        "masters_pct": round(sm.masters_percent, 1),
        "readiness_count": len(md.get("readiness_standards", [])),
        "supporting_count": len(md.get("supporting_standards", [])),
        "standards": standards,
        "tier_students": tier_students,
        "json_str": json_str,
        "teacher_txt": teacher_txt,
        "parent_txt": parent_txt,
        "validation_passed": data.validation_report.get("validation_passed", True),
        "validation_issues": data.validation_report.get("issues", []),
        "json_path": json_file.name,
        "txt_path": txt_file.name,
        "parent_path": parent_file.name,
    }


def _build_dashboard(results: list) -> dict:
    """Aggregate a run's per-assessment results into a cross-assessment view."""
    if not results:
        return {}

    # Weighted overall average (by student count) + headline counts.
    total_students = sum(r["total_students"] for r in results)
    if total_students:
        weighted_avg = round(
            sum(r["avg_pct"] * r["total_students"] for r in results) / total_students, 1
        )
    else:
        weighted_avg = 0.0

    grades = sorted({str(r["grade"]) for r in results if r["grade"] is not None})
    types = sorted({r["type"] for r in results if r["type"]})

    # Per-assessment comparison rows (sorted by grade, then name).
    comparison = sorted(
        results,
        key=lambda r: (str(r["grade"]), (r["assessment_name"] or r["descriptive"])),
    )

    # Group standards across assessments by grade-agnostic canonical code.
    #
    # Grain guard: Reporting Category breakdowns ("RC:R1", "RC:R2", ...) are a
    # different grain than TEKS learning standards and must never land in the
    # same comparison bucket - an RC average and a TEKS average are not
    # comparable numbers. Rather than add a second rollup table (the
    # dashboard template has no section for it), the minimal fix is to
    # exclude reporting-category assessments from this cross-standard rollup
    # entirely. Their canonical codes never enter `by_canon` below, so they
    # can't collide with (or dilute) a learning-standard bucket.
    #
    # Known limitation, out of scope: if an RC rollup were ever added, "RC:R1"
    # from a math assessment would still merge with "RC:R1" from an RLA
    # assessment, since Eduphoria's RC codes aren't subject-qualified.
    by_canon: dict = {}
    for r in results:
        if r.get("breakdown_type") == "reporting_category":
            continue
        label = r["assessment_name"] or r["descriptive"]
        for s in r["standards"]:
            canon = s.get("canonical") or s["code"]
            entry = by_canon.setdefault(
                canon,
                {"canonical": canon, "type": s["type"], "appearances": []},
            )
            entry["appearances"].append(
                {
                    "assessment": label,
                    "grade": r["grade"],
                    "code": s["code"],
                    "proficiency": s["proficiency"],
                    "avg": s["avg"],
                }
            )

    standards_rollup = []
    for canon, e in by_canon.items():
        apps = e["appearances"]
        profs = [a["proficiency"] for a in apps]
        standards_rollup.append(
            {
                "canonical": canon,
                "type": e["type"],
                "count": len(apps),
                "mean_prof": round(sum(profs) / len(profs), 1),
                "min_prof": round(min(profs), 1),
                "max_prof": round(max(profs), 1),
                "appearances": sorted(apps, key=lambda a: a["proficiency"]),
            }
        )

    # Standards seen in 2+ assessments, weakest (lowest mean proficiency) first.
    cross = sorted(
        [s for s in standards_rollup if s["count"] >= 2],
        key=lambda s: (s["mean_prof"], -s["count"]),
    )
    # Single-assessment weak spots, as a fallback / complement.
    single_weak = sorted(
        [s for s in standards_rollup if s["count"] == 1],
        key=lambda s: s["mean_prof"],
    )[:10]

    return {
        "num_assessments": len(results),
        "total_students": total_students,
        "weighted_avg": weighted_avg,
        "grades": grades,
        "types": types,
        "comparison": comparison,
        "cross": cross,
        "single_weak": single_weak,
        "max_avg": max((r["avg_pct"] for r in results), default=100) or 100,
    }


def _resolve_in_output(name: str) -> Path:
    """Resolve a download name strictly inside the current output dir."""
    output_dir = path_config.get_paths().output_dir.resolve()
    candidate = (output_dir / Path(name).name).resolve()
    if candidate.parent != output_dir or not candidate.exists():
        raise NotFound(f"{name} not found in the output folder")
    return candidate


# --- views ------------------------------------------------------------


def index() -> Render:
    resolved = path_config.get_paths()
    existing = sorted(p.name for p in resolved.input_dir.glob("*.xlsx") if not p.name.startswith("~$"))
    existing += sorted(p.name for p in resolved.input_dir.glob("*.csv") if not p.name.startswith("~$"))
    try:
        vault_exists = vault_path().exists()
    except IdentityMigrationError:
        vault_exists = False
    return Render(
        "index.html",
        existing=existing,
        data_dir=str(resolved.data_dir),
        vault_exists=vault_exists,
    )


def coverage(course_id: str, roster_document: dict | None) -> Render:
    """Build the read-only local-ID-to-Canvas-roster coverage report."""
    context = {
        "course_id": str(course_id or ""),
        "mirror_state": "unavailable",
        "mirror_last_success_at": "",
        "report": None,
    }
    if not course_id:
        return Render("coverage.html", **context)
    if not isinstance(roster_document, dict):
        return Render("coverage.html", **context)

    context["mirror_state"] = str(roster_document.get("state") or "unavailable")
    context["mirror_last_success_at"] = str(roster_document.get("last_success_at") or "")
    if not isinstance(roster_document.get("students"), dict):
        return Render("coverage.html", **context)

    try:
        resolved = path_config.get_paths()
        identity = VaultIdentity.from_paths(resolved)
        profile = profile_export.build_profile(resolved, identity=identity)
        linked_students = identity.linked_students()
    except (IdentityMigrationError, OSError):
        context["map_error"] = True
        return Render("coverage.html", **context)

    context["report"] = canvas_join.build_coverage_report(
        profile.get("students") or {},
        linked_students,
        list(roster_document["students"].values()),
    )
    return Render("coverage.html", **context)


def process(anonymize: bool, use_existing: bool, upload_paths: list) -> Redirect:
    """Run the parser over every uploaded and/or existing input file.

    `upload_paths` are files the host has ALREADY validated (extension) and
    saved into `paths.upload_dir`; this view does not touch file storage
    beyond that. Everything else (dedupe, per-file processing, Vault identity
    lifecycle, snapshot saving, profile publishing, upload cleanup, run
    registration) lives here.
    """
    paths = path_config.get_paths()

    try:
        if anonymize:
            migrate_legacy_state(paths)
            vault_identity = VaultIdentity.from_paths(paths)
            # Catch up any history saved before canvas_id existed. Idempotent
            # and cheap at this scale, so it runs on every anonymized
            # processing pass rather than needing its own manual trigger --
            # the same bootstrap pattern migrate_legacy_state already uses.
            backfill_canvas_ids(paths, vault_identity.canvas_id_map())
        else:
            vault_identity = None
    except (IdentityMigrationError, OSError) as e:
        return _error_run(paths, anonymize, str(e))

    work_files: list = list(upload_paths)

    if use_existing:
        for pattern in ("*.xlsx", "*.csv"):
            for p in paths.input_dir.glob(pattern):
                if not p.name.startswith("~$"):
                    work_files.append(p)

    # De-dup by name, keep order.
    seen, deduped = set(), []
    for p in work_files:
        if p.name not in seen:
            seen.add(p.name)
            deduped.append(p)
    work_files = deduped

    results, errors = [], []
    for p in work_files:
        try:
            results.append(_process_file(p, vault_identity, paths.output_dir, strip_demographics=anonymize))
        except Exception as e:  # surface per-file errors without killing the run
            errors.append({"file": p.name, "error": str(e)})

    identity_ready = vault_identity is not None or not anonymize

    # Save longitudinal snapshots for tier-movement tracking. Only de-identified
    # runs are persisted, since tracking relies on stable pseudonyms. If the map
    # did not persist, this run's pseudonyms have no decoder, so a snapshot
    # written now would be permanently unreadable.
    snapshots_saved = 0
    if anonymize and identity_ready:
        for r in results:
            try:
                history_store.save_snapshot(paths, r)
                snapshots_saved += 1
            except Exception as exc:
                operational_log.emit("dataforge.snapshot_save", "failed", error_class=type(exc))

    # Publish the pseudonym-keyed profile into CanvasExpert's AI zone so a
    # later host can group and differentiate from these results. Safe to sync:
    # pseudonyms, standards, and scores only. Skipped when the map did not
    # persist, since those pseudonyms would have no decoder.
    published = None
    if anonymize and identity_ready:
        try:
            published = profile_export.publish_profile(paths, anonymizer=vault_identity)
        except profile_export.SharedPublishError as e:
            errors.append({"file": "standards profile", "error": str(e)})

    # Remove transient web uploads so raw PII does not accumulate on disk.
    for up in upload_paths:
        try:
            up.unlink()
        except OSError:
            pass

    if not results and not errors:
        return Redirect("index")

    run_id = uuid.uuid4().hex[:8]
    RUNS[run_id] = {
        "results": results,
        "errors": errors,
        "anonymized": anonymize,
        "output_dir": str(paths.output_dir),
        "snapshots_saved": snapshots_saved,
        "published_profile": str(published) if published else None,
    }
    return Redirect("results", run_id=run_id)


def dashboard(run_id: str):
    run = RUNS.get(run_id)
    if not run:
        return Redirect("index")
    return Render(
        "dashboard.html",
        run_id=run_id,
        dash=_build_dashboard(run["results"]),
        anonymized=run["anonymized"],
    )


def groups(run_id: str):
    run = RUNS.get(run_id)
    if not run:
        return Redirect("index")
    # Slim payload for the client-side grouper: only what tiering needs.
    payload = [
        {
            "id": r["file_id"],
            "name": r["assessment_name"] or r["descriptive"],
            "grade": r["grade"],
            "type": r["type"],
            "students": r["tier_students"],
        }
        for r in run["results"]
    ]
    return Render(
        "groups.html",
        run_id=run_id,
        assessments=payload,
        anonymized=run["anonymized"],
    )


def history() -> Render:
    paths = path_config.get_paths()
    snapshots = history_store.list_snapshots(paths)
    return Render("history.html", snapshots=snapshots)


def history_update(snap_id: str, new_date: str) -> Redirect:
    paths = path_config.get_paths()
    history_store.update_date(paths, snap_id, (new_date or "").strip())
    return Redirect("history")


def history_delete(snap_id: str) -> Redirect:
    paths = path_config.get_paths()
    history_store.delete_snapshot(paths, snap_id)
    return Redirect("history")


def export_standards_profile() -> BytesDownload:
    """Pseudonym-keyed standards profile, for grouping and differentiation.

    SAFE to hand to another tool: pseudonyms, standard codes, and scores only.
    Resolving a pseudonym to a real student happens locally against the
    Identity Vault and never through this file.
    """
    paths = path_config.get_paths()
    try:
        identity = VaultIdentity.from_paths(paths)
    except IdentityMigrationError:
        identity = None
    profile = profile_export.build_profile(paths, identity=identity)
    profile["grouping"] = profile_export.group_by_standard(profile)
    data = json.dumps(profile, indent=2, ensure_ascii=False).encode("utf-8")
    return BytesDownload(
        data,
        mimetype="application/json",
        download_name="dataforge_standards_profile.json",
    )


def results(run_id: str):
    run = RUNS.get(run_id)
    if not run:
        return Redirect("index")
    return Render(
        "results.html",
        run_id=run_id,
        results=run["results"],
        errors=run["errors"],
        anonymized=run["anonymized"],
    )


def download(name: str) -> FileDownload:
    return FileDownload(_resolve_in_output(name))


def download_all(run_id: str) -> BytesDownload:
    run = RUNS.get(run_id)
    if not run:
        raise NotFound(f"no run {run_id}")
    output_dir = Path(run["output_dir"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for r in run["results"]:
            for key in ("json_path", "txt_path", "parent_path"):
                p = output_dir / r[key]
                if p.exists():
                    z.write(p, p.name)
    return BytesDownload(
        buf.getvalue(),
        mimetype="application/zip",
        download_name=f"dataforge_results_{run_id}.zip",
    )
