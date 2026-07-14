"""Canonical workspace ownership and non-destructive compatibility helpers.

The synced workspace is teacher-visible data.  Keep path construction here so
callers cannot accidentally create a second student tree or put new machine
state under the historical ``FeedbackExpert`` folder.
"""

from __future__ import annotations

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
SYSTEM_SUBFOLDERS = ("Identity Vault", "PowerGrader", "Audits", "Archive")
LEGACY_FEEDBACK_NAME = "FeedbackExpert"

# Compatibility aliases retained for imports and old UI wording.  New code
# must use the canonical helpers below.
FEEDBACK_NAME = LEGACY_FEEDBACK_NAME
FEEDBACK_SUBFOLDERS = ["SAFE", "PRIVATE", "_system"]

MAX_COMPONENT_LENGTH = 120
MAX_PATH_LENGTH = 240
_BAD_COMPONENT = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_BAD_ID = re.compile(r"[^A-Za-z0-9._-]+")


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


def course_folder(course_name, course_id, root=None):
    base = _root_or_workspace(root)
    return bounded_join(base, COURSES_NAME, named_id_folder(course_name, course_id)) if base else None


def assignment_folder(course_name, course_id, assignment_name, assignment_id, root=None):
    base = _root_or_workspace(root)
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
    if not os.path.isdir(directory):
        return []
    return [candidate for candidate in glob.glob(os.path.join(directory, "*assignment_evidence_manifest*.json"))
            if os.path.normcase(os.path.abspath(candidate)) != os.path.normcase(os.path.abspath(path))]


def read_assignment_evidence_manifest(course_name, course_id, assignment_name, assignment_id, root=None):
    path = assignment_evidence_manifest_path(course_name, course_id, assignment_name, assignment_id, root)
    if not path or assignment_evidence_conflicts(course_name, course_id, assignment_name, assignment_id, root):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
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
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".assignment_evidence_", suffix=".partial", dir=os.path.dirname(path), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
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
                  mode="assisted", *, run_timestamp=None, root=None):
    base = _root_or_workspace(root)
    if not base:
        return None
    stamp = run_timestamp or datetime.now().strftime("%Y%m%d-%H%M%S-%f")
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
