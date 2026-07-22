"""Canonical workspace ownership and non-destructive compatibility helpers.

The synced workspace is teacher-visible data.  Keep path construction here so
callers cannot accidentally create a second student tree or put new machine
state under the historical ``FeedbackExpert`` folder.
"""

from __future__ import annotations

import fnmatch
import glob
import json
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path


MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.dirname(MODULE_DIR)
REPO_ROOT = os.path.dirname(API_DIR)
CONFIG_PATH = os.path.join(MODULE_DIR, "config.json")
DEFAULT_DOCS_DIR = os.path.join(API_DIR, "default_docs")
WORKSPACE_NAME = "CanvasExpert"

# Existing authoring folders remain supported.  These are not the home for
# downloaded student work or machine-owned PowerGrader state.
WORKSPACE_SUBFOLDERS = [
    "AI-TA", "Rubrics", "Quizzes", "Assignments", "Pages", "Exports",
    "Calendars", "Source Materials",
]

COURSES_NAME = "Courses"
AI_PACKETS_NAME = "AI Packets (Pseudonymized)"
STUDENT_REPORTS_NAME = "Student Reports"
SYSTEM_NAME = "_System"
SYSTEM_SUBFOLDERS = ("Identity Vault", "PowerGrader", "Audits", "Archive",
                     "Canvas Catalog", "Canvas Mirror")
CANVAS_CATALOG_NAME = "Canvas Catalog"
CANVAS_MIRROR_NAME = "Canvas Mirror"
LEGACY_FEEDBACK_NAME = "FeedbackExpert"

# Compatibility aliases retained for imports and old UI wording.  New code
# must use the canonical helpers below.
FEEDBACK_NAME = LEGACY_FEEDBACK_NAME
FEEDBACK_SUBFOLDERS = ["SAFE", "PRIVATE", "_system"]

MAX_COMPONENT_LENGTH = 120
MAX_PATH_LENGTH = 240
TEACHER_VISIBLE_BUDGET = 230
_BAD_COMPONENT = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_BAD_ID = re.compile(r"[^A-Za-z0-9._-]+")

# Deterministic short-hash length for compact path components.
# 8 hex chars → 2^32 namespace, negligible collision risk within one assignment.
_COMPACT_HASH_LENGTH = 8


class TeacherVisiblePathBudgetError(ValueError):
    """Raised when even the compact form of a teacher-visible path exceeds
    the 230-character budget."""


def _deterministic_hash(text: str, length: int = _COMPACT_HASH_LENGTH) -> str:
    """Return a deterministic lowercase hex hash of *text*.

    Uses Python's built-in hash() salted with a fixed seed so results are
    stable across interpreter runs on the same platform.  The hex digest is
    short enough to fit within the path budget.
    """
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


_SHA256_ABBREV = _deterministic_hash


def teacher_visible_path(
    base: str,
    *components: str,
    filename: str = "",
    reserve: int = 0,
) -> str:
    """Build a teacher-visible absolute path guaranteed to be at most 230 characters.

    Parameters
    ----------
    base:
        Absolute base directory (e.g. workspace root).
    *components:
        Ordered path segments to join under *base*.  Each may be a plain
        string or a ``(display, stable_id)`` tuple.  For tuples, the
        component becomes ``<display> — <id>`` and the stable id portion
        is always preserved in the compact fallback.
    filename:
        Optional final file name with extension.
    reserve:
        Extra characters to reserve for projected suffix components that
        will be appended by the caller *after* this call (e.g. batch
        index, extension).  When given, the returned path is *shorter* so
        the caller's full path still fits.

    Returns
    -------
    str
        The projected plain (unprefixed) absolute path, at most
        ``TEACHER_VISIBLE_BUDGET`` characters.

    Raises
    ------
    TeacherVisiblePathBudgetError
        When even the compact form (shortened display portions, stable-id
        suffixes preserved) cannot fit within the budget.
    """
    budget = TEACHER_VISIBLE_BUDGET - reserve
    segments: list[str] = [os.path.abspath(base)]

    # First pass: assemble with full display names.
    raw_segments: list[str] = []
    for c in components:
        if isinstance(c, tuple):
            display, stable_id = c
            raw_segments.append(f"{display} — {stable_id}")
        else:
            raw_segments.append(str(c))

    # Try full-readable form first.
    def _project(seg: list[str]) -> str:
        parts = [str(s) for s in seg]
        if filename:
            parts.append(str(filename))
        return os.path.join(*parts)

    candidate = _project(segments + raw_segments)
    if len(candidate) <= budget:
        return candidate

    # Compact fallback: shorten display portions, keep stable IDs.
    compact_segments: list[str] = list(segments)
    for c in components:
        if isinstance(c, tuple):
            display, stable_id = c
            # Use a deterministic short hash of the full stable-id-bearing
            # name so that two different assignments with the same stable ID
            # still produce distinct paths.
            short_hash = _deterministic_hash(f"{display}—{stable_id}")
            compact_segments.append(f"{short_hash} — {stable_id}")
        else:
            # Non-identity component: shorten aggressively.
            short = _deterministic_hash(str(c))
            compact_segments.append(short)

    candidate = _project(compact_segments)
    if len(candidate) <= budget:
        return candidate

    # Strip display portions entirely: keep only the hash.
    minimal_segments: list[str] = list(segments)
    for c in components:
        if isinstance(c, tuple):
            _display, stable_id = c
            minimal_segments.append(stable_id)
        else:
            minimal_segments.append(_deterministic_hash(str(c)))

    candidate = _project(minimal_segments)
    if len(candidate) <= budget:
        return candidate

    raise TeacherVisiblePathBudgetError(
        f"Path too deep for teacher-visible output "
        f"(projected {len(candidate)} > {budget} budget)"
    )


def _machine_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def onedrive_root():
    for name in ("OneDriveCommercial", "OneDrive"):
        path = os.environ.get(name, "").strip()
        if path:
            return path
    return None


def workspace_root():
    machine = _machine_config()
    override = str(machine.get("workspace_path") or "").strip()
    if override:
        return override
    root = onedrive_root()
    if root:
        return os.path.join(root, WORKSPACE_NAME)
    return None


def safe_component(value, max_len: int = MAX_COMPONENT_LENGTH, fallback: str = "_unnamed") -> str:
    """Return a readable Windows/POSIX-safe path component.

    The result is deliberately not an identity scrubber; Canvas IDs are kept in
    the containing folder name as the stable, private collision suffix.
    """
    text = _BAD_COMPONENT.sub("_", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip(" .")
    if not text:
        text = fallback
    text = text[:max(1, int(max_len))].rstrip(" .") or fallback
    if text.upper().split(".", 1)[0] in {
        "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        text += "_"
    return text


def safe_id(value, fallback: str = "unknown") -> str:
    text = _BAD_ID.sub("_", str(value or "").strip())
    return text.strip("._-") or fallback


def named_id_folder(display_name, stable_id, *, max_len: int = MAX_COMPONENT_LENGTH) -> str:
    """Build ``<readable display> — <stable id>`` without losing the ID."""
    suffix = f" — {safe_id(stable_id)}"
    available = max(1, int(max_len) - len(suffix))
    return safe_component(display_name, available) + suffix


def bounded_join(base: str, *parts: str, max_path: int = MAX_PATH_LENGTH) -> str:
    """Join readable components and shrink display portions for Windows limits."""
    values = [str(base)] + [str(part) for part in parts]
    path = os.path.join(*values)
    if len(path) <= max_path:
        return path
    # Keep the stable ID suffix and shorten human-facing portions first.
    for _ in range(len(values) * 3):
        changed = False
        for index in range(len(values) - 1, 0, -1):
            part = values[index]
            if " — " not in part:
                continue
            label, suffix = part.split(" — ", 1)
            excess = max(1, len(path) - max_path)
            target_len = max(1, len(part) - excess)
            label_len = max(1, target_len - len(suffix) - 3)
            if label_len >= len(label):
                continue
            values[index] = f"{safe_component(label, label_len)} — {suffix}"
            path = os.path.join(*values)
            changed = True
            if len(path) <= max_path:
                break
        if len(path) <= max_path or not changed:
            break
    return path


def extended_path(path: str) -> str:
    """Return a form of ``path`` safe for file I/O past Windows' 260-char limit.

    ``bounded_join`` keeps our *directory* names short, but a deep workspace
    (e.g. a long OneDrive root + long course/assignment names) can still push a
    full *file* path over the legacy MAX_PATH ceiling — at which point
    ``open()``/``makedirs`` raise ``FileNotFoundError [Errno 2]`` even though the
    parent directory exists. On Windows, prefixing an absolute, backslash-only
    path with ``\\\\?\\`` opts that single call out of MAX_PATH (raising the
    limit to ~32,767), the supported way to reach such files without the OS-wide
    LongPathsEnabled policy.

    The prefix is applied ONLY when the absolute path approaches the limit
    (>= ``MAX_PATH_LENGTH``). Short paths are returned unchanged so the vast
    majority of I/O keeps its exact current behavior — the ``\\\\?\\`` form
    disables normalization and has subtle edge cases, so it is used only where a
    normal call would actually fail. Non-Windows paths and already-prefixed
    paths are returned as-is (idempotent).
    """
    if os.name != "nt" or not path:
        return path
    if path.startswith("\\\\?\\") or path.startswith("\\\\.\\"):
        return path
    abs_path = os.path.abspath(path)
    if len(abs_path) < MAX_PATH_LENGTH:
        return path
    if abs_path.startswith("\\\\"):
        # UNC share: \\server\share -> \\?\UNC\server\share
        return "\\\\?\\UNC\\" + abs_path[2:]
    return "\\\\?\\" + abs_path


def _root_or_workspace(root=None):
    return root if root is not None else workspace_root()


def _join_root(name: str, root=None):
    base = _root_or_workspace(root)
    return os.path.join(base, name) if base else None


def folder(name):
    return _join_root(name)


def courses_root(root=None):
    return _join_root(COURSES_NAME, root)


def ai_packets_root(root=None):
    return _join_root(AI_PACKETS_NAME, root)


def student_reports_root(root=None):
    return _join_root(STUDENT_REPORTS_NAME, root)


def system_root(root=None):
    return _join_root(SYSTEM_NAME, root)


def system_folder(name: str | None = None, root=None):
    base = system_root(root)
    if not base:
        return None
    return os.path.join(base, name) if name else base


def identity_vault_dir(root=None):
    return system_folder("Identity Vault", root)


def powergrader_root(root=None):
    return system_folder("PowerGrader", root)


def powergrader_sessions_dir(root=None):
    base = powergrader_root(root)
    return os.path.join(base, "Sessions") if base else None


def powergrader_jobs_dir(root=None):
    base = powergrader_root(root)
    return os.path.join(base, "Jobs") if base else None


def audits_dir(root=None):
    return system_folder("Audits", root)


def archive_dir(root=None):
    return system_folder("Archive", root)


def canvas_catalog_root(root=None):
    """Return the durable, student-data-free Canvas Catalog root."""
    return system_folder(CANVAS_CATALOG_NAME, root)


def course_catalog_dir(course_id, root=None):
    """Return the stable per-course catalog directory owned by Canvas course ID."""
    base = canvas_catalog_root(root)
    return os.path.join(base, safe_id(course_id)) if base else None


def course_catalog_path(course_id, root=None):
    directory = course_catalog_dir(course_id, root)
    return os.path.join(directory, "catalog.v1.json") if directory else None


def course_catalog_previous_path(course_id, root=None):
    directory = course_catalog_dir(course_id, root)
    return os.path.join(directory, "catalog.v1.previous.json") if directory else None


def course_catalog_v2_path(course_id, root=None):
    directory = course_catalog_dir(course_id, root)
    return os.path.join(directory, "catalog.v2.json") if directory else None


def course_catalog_v2_previous_path(course_id, root=None):
    directory = course_catalog_dir(course_id, root)
    return os.path.join(directory, "catalog.v2.previous.json") if directory else None


def canvas_mirror_root(root=None):
    """Return the CanvasMirror root — the disposable local mirror of Canvas
    course facts. Everything under it is rebuildable by re-sync."""
    return system_folder(CANVAS_MIRROR_NAME, root)


def course_mirror_dir(course_id, root=None):
    """Return the stable per-course mirror directory owned by Canvas course ID."""
    base = canvas_mirror_root(root)
    return os.path.join(base, safe_id(course_id)) if base else None


def course_folder(course_name, course_id, root=None):
    base = _root_or_workspace(root)
    return bounded_join(base, COURSES_NAME, named_id_folder(course_name, course_id)) if base else None


def assignment_folder(course_name, course_id, assignment_name, assignment_id, root=None, *, reserve=0):
    base = _root_or_workspace(root)
    if not base:
        return None
    if reserve:
        return teacher_visible_path(
            base,
            (COURSES_NAME, COURSES_NAME),
            (named_id_folder(course_name, course_id), course_id),
            ("Assignments", "Assignments"),
            (named_id_folder(assignment_name, assignment_id), assignment_id),
            reserve=reserve,
        )
    return bounded_join(base, COURSES_NAME, named_id_folder(course_name, course_id),
                       "Assignments", named_id_folder(assignment_name, assignment_id)) if base else None


def student_folder(course_name, course_id, assignment_name, assignment_id,
                   student_name, user_id, root=None):
    base = _root_or_workspace(root)
    # sortable_name is already ``Last, First`` when Canvas provides it.  The
    # caller may pass either form; preserving the display text is intentional.
    return bounded_join(base, COURSES_NAME, named_id_folder(course_name, course_id),
                        "Assignments", named_id_folder(assignment_name, assignment_id),
                        "Student Work", named_id_folder(student_name, user_id)) if base else None


def attempt_folder(course_name, course_id, assignment_name, assignment_id,
                   student_name, user_id, attempt=1, root=None):
    base = _root_or_workspace(root)
    attempt_text = safe_id(attempt, "1")
    return bounded_join(base, COURSES_NAME, named_id_folder(course_name, course_id),
                        "Assignments", named_id_folder(assignment_name, assignment_id),
                        "Student Work", named_id_folder(student_name, user_id),
                        f"Attempt {attempt_text}") if base else None


ASSIGNMENT_EVIDENCE_MANIFEST = "assignment_evidence_manifest.json"


def assignment_evidence_manifest_path(course_name, course_id, assignment_name, assignment_id, root=None):
    """Return the private, canonical manifest path for one assignment."""
    folder = assignment_folder(course_name, course_id, assignment_name, assignment_id, root)
    return os.path.join(folder, ASSIGNMENT_EVIDENCE_MANIFEST) if folder else None


def managed_evidence_path(course_name, course_id, assignment_name, assignment_id,
                          student_name, user_id, attempt, evidence_id, filename, root=None):
    """Return a deterministic managed-original path; filenames are never identity."""
    base = attempt_folder(course_name, course_id, assignment_name, assignment_id,
                          student_name, user_id, attempt, root)
    if not base or not evidence_id:
        return None
    return bounded_join(base, f"{safe_id(evidence_id)} — {safe_component(filename, 150)}")


def assignment_evidence_conflicts(course_name, course_id, assignment_name, assignment_id, root=None):
    """Find OneDrive-style competing manifests without selecting or modifying either."""
    path = assignment_evidence_manifest_path(course_name, course_id, assignment_name, assignment_id, root)
    if not path:
        return []
    directory = os.path.dirname(path)
    if not os.path.isdir(extended_path(directory)):
        return []
    # os.listdir(extended) + fnmatch instead of glob: it enumerates a deep
    # (>260) directory correctly and keeps candidates as plain paths, so the
    # canonical-path comparison below is unaffected by any \\?\ prefix.
    canonical = os.path.normcase(os.path.abspath(path))
    conflicts = []
    for name in os.listdir(extended_path(directory)):
        if not fnmatch.fnmatch(name, "*assignment_evidence_manifest*.json"):
            continue
        candidate = os.path.join(directory, name)
        if os.path.normcase(os.path.abspath(candidate)) != canonical:
            conflicts.append(candidate)
    return conflicts


def read_assignment_evidence_manifest(course_name, course_id, assignment_name, assignment_id, root=None):
    path = assignment_evidence_manifest_path(course_name, course_id, assignment_name, assignment_id, root)
    if not path or assignment_evidence_conflicts(course_name, course_id, assignment_name, assignment_id, root):
        return None
    try:
        with open(extended_path(path), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict) or str(data.get("course_id")) != str(course_id) or str(data.get("assignment_id")) != str(assignment_id):
        return None
    return data


def write_assignment_evidence_manifest(manifest: dict, *, course_name, course_id, assignment_name, assignment_id, root=None):
    """Atomically replace a validated private manifest after evidence is finalized."""
    path = assignment_evidence_manifest_path(course_name, course_id, assignment_name, assignment_id, root)
    if not path or str(manifest.get("course_id")) != str(course_id) or str(manifest.get("assignment_id")) != str(assignment_id):
        return None
    if assignment_evidence_conflicts(course_name, course_id, assignment_name, assignment_id, root):
        return None
    # os-level via extended_path so a deep assignment folder survives Windows'
    # 260-char limit; mkstemp(dir=extended) yields an already-prefixed temporary.
    os.makedirs(extended_path(os.path.dirname(path)), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".assignment_evidence_", suffix=".partial", dir=extended_path(os.path.dirname(path)), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, extended_path(path))
        return path
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def ai_assignment_root(course_name, course_id, assignment_name, assignment_id, root=None):
    base = _root_or_workspace(root)
    if not base:
        return None
    return bounded_join(base, AI_PACKETS_NAME, named_id_folder(course_name, course_id),
                        named_id_folder(assignment_name, assignment_id))


def ai_run_folder(course_name, course_id, assignment_name, assignment_id,
                  mode="assisted", *, run_timestamp=None, root=None, reserve=0):
    base = _root_or_workspace(root)
    if not base:
        return None
    stamp = run_timestamp or datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    if reserve:
        return teacher_visible_path(
            base,
            (AI_PACKETS_NAME, AI_PACKETS_NAME),
            (named_id_folder(course_name, course_id), course_id),
            (named_id_folder(assignment_name, assignment_id), assignment_id),
            f"{safe_component(stamp, 32)} — {safe_component(mode, 32)}",
            reserve=reserve,
        )
    return bounded_join(base, AI_PACKETS_NAME, named_id_folder(course_name, course_id),
                        named_id_folder(assignment_name, assignment_id),
                        f"{safe_component(stamp, 32)} — {safe_component(mode, 32)}")


def ai_student_folder(course_name, course_id, assignment_name, assignment_id,
                      mode, pseudonym, *, run_timestamp=None, root=None):
    base = _root_or_workspace(root)
    if not base:
        return None
    stamp = run_timestamp or datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return bounded_join(base, AI_PACKETS_NAME, named_id_folder(course_name, course_id),
                        named_id_folder(assignment_name, assignment_id),
                        f"{safe_component(stamp, 32)} — {safe_component(mode, 32)}",
                        "Students", safe_component(pseudonym, 80))


def _ensure_dir(path):
    if path:
        os.makedirs(path, exist_ok=True)
    return path


def _default_rubric_files():
    source_dir = os.path.join(DEFAULT_DOCS_DIR, "Rubrics")
    if os.path.isdir(source_dir):
        return sorted(glob.glob(os.path.join(source_dir, "*.txt")))
    return sorted(glob.glob(os.path.join(API_DIR, "rubrics", "*.txt")))


def _seed_folder_if_missing(source_dir, target_dir):
    if not os.path.isdir(source_dir):
        return
    for root, _, files in os.walk(source_dir):
        rel_dir = os.path.relpath(root, source_dir)
        dest_root = target_dir if rel_dir == "." else os.path.join(target_dir, rel_dir)
        os.makedirs(dest_root, exist_ok=True)
        for name in files:
            source = os.path.join(root, name)
            target = os.path.join(dest_root, name)
            if os.path.exists(target):
                continue
            shutil.copy2(source, target)


def _seed_workspace_readme(root):
    path = os.path.join(root, "README (workspace privacy).txt")
    if os.path.exists(path):
        return path
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "Canvas Expert workspace\n"
            "=======================\n\n"
            "Courses/ contains real-name student work and is PRIVATE.\n"
            "_System/ contains the identity vault, PowerGrader state, and audit files; it is PRIVATE.\n"
            "AI Packets (Pseudonymized)/ contains pseudonymized artifacts. Review every file before sharing;\n"
            "pseudonyms do not guarantee anonymity and visible content may still identify a student.\n"
            "Student Reports/ contains derived teacher reports.\n\n"
            "Canvas Expert does not automatically rename, move, overwrite, or delete existing legacy folders.\n"
        )
    return path


def ensure_workspace():
    """Create canonical roots and seed defaults without touching legacy data."""
    root = workspace_root()
    if not root:
        return None
    os.makedirs(root, exist_ok=True)
    for subfolder in WORKSPACE_SUBFOLDERS:
        target_dir = os.path.join(root, subfolder)
        os.makedirs(target_dir, exist_ok=True)
        _seed_folder_if_missing(os.path.join(DEFAULT_DOCS_DIR, subfolder), target_dir)
    for canonical in (COURSES_NAME, AI_PACKETS_NAME, STUDENT_REPORTS_NAME, SYSTEM_NAME):
        os.makedirs(os.path.join(root, canonical), exist_ok=True)
    for sub in SYSTEM_SUBFOLDERS:
        os.makedirs(os.path.join(root, SYSTEM_NAME, sub), exist_ok=True)
    os.makedirs(os.path.join(root, SYSTEM_NAME, "PowerGrader", "Sessions"), exist_ok=True)
    os.makedirs(os.path.join(root, SYSTEM_NAME, "PowerGrader", "Jobs"), exist_ok=True)

    rubric_dir = os.path.join(root, "Rubrics")
    for source in _default_rubric_files():
        target = os.path.join(rubric_dir, os.path.basename(source))
        if not os.path.exists(target):
            shutil.copy2(source, target)
    _seed_workspace_readme(root)
    return root


def legacy_feedback_root():
    root = workspace_root()
    path = os.path.join(root, LEGACY_FEEDBACK_NAME) if root else None
    return path if path and os.path.isdir(path) else None


def feedback_root():
    """Return the legacy FeedbackExpert root only when it already exists.

    This function is intentionally read-only: calling it cannot create the old
    tree again.
    """
    return legacy_feedback_root()


def feedback_folder(sub):
    """Resolve an old feedback folder for compatibility, or a canonical alias.

    Existing legacy folders win.  If no legacy tree exists, semantic SAFE,
    PRIVATE, and system aliases point at their canonical homes so old helper
    code can be retired incrementally without creating ``FeedbackExpert``.
    """
    legacy = legacy_feedback_root()
    if legacy:
        translation = {
            "1_Inbox": "PRIVATE", "2_ForLLM": "SAFE", "3_FromLLM": "SAFE",
            "4_ToEnter": "PRIVATE", "_vault": os.path.join("_system", "vault"),
            "_archive": os.path.join("_system", "archive"),
            "_audit": os.path.join("_system", "audit"),
        }
        return os.path.join(legacy, translation.get(sub, sub))
    if sub in {"SAFE", "2_ForLLM", "3_FromLLM"}:
        return ai_packets_root()
    if sub in {"PRIVATE", "1_Inbox", "4_ToEnter"}:
        return courses_root()
    if sub in {"_vault", "vault"}:
        return identity_vault_dir()
    if sub in {"_audit", "audit"}:
        return audits_dir()
    if sub in {"_archive", "archive"}:
        return archive_dir()
    return None


def feedback_legacy_folder(sub):
    legacy = legacy_feedback_root()
    if not legacy:
        return None
    return feedback_folder(sub)


def compatibility_paths(filename: str, *, kind: str = "session") -> list[str]:
    """Return legacy machine-state candidates, newest/canonical first elsewhere."""
    root = workspace_root()
    if not root:
        return []
    if kind == "session":
        old = [os.path.join(root, "PowerGrader", filename),
               os.path.join(root, LEGACY_FEEDBACK_NAME, "PRIVATE", "PowerGrader", filename)]
    elif kind == "job":
        old = [os.path.join(root, "PowerGrader", filename),
               os.path.join(root, LEGACY_FEEDBACK_NAME, "PRIVATE", "PowerGrader", filename)]
    else:
        old = [os.path.join(root, LEGACY_FEEDBACK_NAME, "_system", filename)]
    return [p for p in old if os.path.isfile(p)]


def verified_copy_if_absent(source: str, destination: str) -> bool:
    """Copy machine-owned compatibility state without overwrite or deletion."""
    if not os.path.isfile(source) or os.path.exists(destination):
        return False
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    shutil.copy2(source, destination)
    try:
        return os.path.getsize(source) == os.path.getsize(destination)
    except OSError:
        return False


def path_within_workspace(path: str, root=None) -> bool:
    base = _root_or_workspace(root)
    if not base or not path:
        return False
    try:
        return os.path.commonpath([os.path.realpath(path), os.path.realpath(base)]) == os.path.realpath(base)
    except ValueError:
        return False
