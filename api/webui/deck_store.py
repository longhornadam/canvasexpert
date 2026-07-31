"""SmartDeck storage and retrieval.

Pure functions for saving, listing, loading, archiving, and deleting SmartDecks.
Decks are stored as JSON files in the workspace Library/SmartDecks/Decks folder,
with archived revisions moved to Decks/Archived. Deleted decks move to
_System/Archive/SmartDecks/.

All functions include path jailing: any resolved path must lie inside the
SmartDecks folder (not just the workspace root). This guards against traversal
attacks on caller-supplied deck_id values.
"""
import json
import os
import glob
import tempfile
import shutil
from pathlib import Path

from api.webui import workspace, sf


def _decks_dir():
    """Return <workspace>/Library/SmartDecks/Decks, or None if no workspace."""
    base = workspace.library_folder("SmartDecks")
    if base is None:
        return None
    return os.path.join(base, "Decks")


def _archived_dir():
    """Return <workspace>/Library/SmartDecks/Decks/Archived."""
    base = _decks_dir()
    if base is None:
        return None
    return os.path.join(base, "Archived")


def _deleted_dir():
    """Return <workspace>/_System/Archive/SmartDecks, where delete_deck moves files."""
    archive_root = workspace.system_folder("Archive")
    if archive_root is None:
        return None
    return os.path.join(archive_root, "SmartDecks")


def _smartdecks_base():
    """Return <workspace>/Library/SmartDecks for path jailing checks."""
    base = workspace.library_folder("SmartDecks")
    return os.path.realpath(base) if base else None


def _move_preserving(source: str, destination: str, what: str) -> list[str]:
    """Move a file, refusing to overwrite an existing destination.

    shutil.move falls back to copy-then-delete when os.rename fails, which on
    Windows means an occupied destination is silently overwritten. Every move in
    this module is an archive or a soft delete, so clobbering the destination is
    the one outcome this storage layer promises cannot happen. Revision numbers
    are unique per date (see next_revision), so a collision here means a file
    predating that guarantee -- refuse and say so rather than destroy it.

    Returns [] on success, or a single problem string prefixed with `what`.
    """
    if os.path.exists(destination):
        return [f"{what}: a different deck is already stored at "
                f"{os.path.basename(destination)}; nothing was moved"]
    try:
        shutil.move(source, destination)
    except (OSError, shutil.Error) as e:
        return [f"{what}: {e}"]
    return []


def _is_path_jailed(path: str) -> bool:
    """Verify a resolved path is inside Library/SmartDecks.

    Uses os.path.commonpath for strict jailing (not just workspace root).
    Returns False if path resolution fails or is outside the allowed directory.
    """
    if not path:
        return False
    try:
        base = _smartdecks_base()
        if not base:
            return False
        resolved = os.path.realpath(path)
        return os.path.commonpath([resolved, base]) == base
    except (ValueError, OSError):
        return False


def next_revision(date: str) -> int:
    """Return the next free revision number for a date.

    Scans <date>.r*.json in every location a deck can live: active, Decks/Archived,
    and _System/Archive/SmartDecks. Revision numbers have to be unique per date
    across all three, not just within the active folder. Scanning only the active
    folder restarts at r1 once a date's decks have all been archived or deleted,
    and the next archive/delete then moves a fresh r1 onto the stored one.

    Returns 1 if no revision of this date exists anywhere.
    """
    highest = 0
    for directory in (_decks_dir(), _archived_dir(), _deleted_dir()):
        if directory is None or not os.path.isdir(directory):
            continue
        for path in glob.glob(os.path.join(directory, f"{date}.r*.json")):
            filename = os.path.basename(path)
            # Extract revision number from filename like "2026-08-14.r2.json"
            try:
                rev_num = int(filename.split(".")[-2][1:])  # "r2" -> 2
            except (ValueError, IndexError):
                # Stray non-matching file, ignore it
                continue
            highest = max(highest, rev_num)

    return highest + 1


def save_deck(data: dict) -> tuple[dict | None, list[str]]:
    """Validate and save a deck, archiving any prior revisions for the same date.

    Runs sf.validate(data) first. Returns (None, problems) if validation fails
    (writes nothing). On success: archives existing active revisions for this
    date, computes the next revision number, atomically writes the JSON to
    <decks_dir>/<date>.r<revision>.json, and returns
    ({"deck_id": ..., "path": ..., "revision": ...}, []).

    Any storage-level error returns (None, [reason]), never raises.
    """
    # Validate the deck first
    problems = sf.validate(data)
    if problems:
        return None, problems

    date = data.get("date", "")
    decks_dir = _decks_dir()
    if decks_dir is None:
        return None, ["no workspace available"]

    try:
        # Create directory if needed
        os.makedirs(decks_dir, exist_ok=True)

        # Compute next revision BEFORE archiving (so we see the current active files)
        revision = next_revision(date)
        deck_id = f"{date}.r{revision}"
        final_path = os.path.join(decks_dir, f"{deck_id}.json")

        # Archive existing revisions for this date
        archived_dir = _archived_dir()
        pattern = os.path.join(decks_dir, f"{date}.r*.json")
        for old_file in glob.glob(pattern):
            try:
                os.makedirs(archived_dir, exist_ok=True)
            except OSError as e:
                return None, [f"failed to archive prior revision: {e}"]
            old_name = os.path.basename(old_file)
            archive_dest = os.path.join(archived_dir, old_name)
            move_problems = _move_preserving(
                old_file, archive_dest, "failed to archive prior revision")
            if move_problems:
                return None, move_problems

        # Verify the path is jailed
        if not _is_path_jailed(final_path):
            return None, ["path traversal detected"]

        # Atomic write using tempfile pattern
        fd = None
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(
                prefix=".smartdeck_",
                suffix=".partial",
                dir=decks_dir,
                text=True
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, final_path)
        except (OSError, IOError) as e:
            if temporary and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
            return None, [f"failed to write deck: {e}"]

        return {"deck_id": deck_id, "path": final_path, "revision": revision}, []

    except Exception as e:
        return None, [f"unexpected error saving deck: {e}"]


def list_decks(status: str = "active") -> list[dict]:
    """List all SmartDecks, either active or archived.

    status='active' lists decks in _decks_dir() (not Archived).
    status='archived' lists decks in _archived_dir().
    Returns a list of dicts with {deck_id, date, title, revision, path}.
    Returns empty list if no workspace or directory missing -- never raises.
    """
    if status == "active":
        search_dir = _decks_dir()
    elif status == "archived":
        search_dir = _archived_dir()
    else:
        return []

    if search_dir is None or not os.path.isdir(search_dir):
        return []

    decks = []
    for filepath in glob.glob(os.path.join(search_dir, "*.json")):
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            filename = os.path.basename(filepath)
            # Remove .json extension to get deck_id
            deck_id = filename[:-5] if filename.endswith(".json") else filename
            # Parse revision from filename like "2026-08-14.r2"
            parts = deck_id.rsplit(".r", 1)
            if len(parts) == 2:
                date = parts[0]
                try:
                    revision = int(parts[1])
                except ValueError:
                    revision = 0
            else:
                date = deck_id
                revision = 0

            decks.append({
                "deck_id": deck_id,
                "date": date,
                "title": data.get("title", ""),
                "revision": revision,
                "path": filepath,
            })
        except (OSError, json.JSONDecodeError):
            # Skip unreadable or malformed files
            continue

    return decks


def load_deck(deck_id: str) -> tuple[dict | None, list[str]]:
    """Load a deck by deck_id from active or archived directory.

    Tries _decks_dir() first, then _archived_dir().
    Returns (deck_data, []) on success, (None, [reason]) if not found or unreadable.
    """
    if not deck_id or not isinstance(deck_id, str):
        return None, ["invalid deck_id"]

    # Path jail: verify the final path will be inside SmartDecks
    decks_dir = _decks_dir()
    if decks_dir is None:
        return None, ["no workspace available"]

    active_path = os.path.join(decks_dir, f"{deck_id}.json")
    if not _is_path_jailed(active_path):
        return None, ["path traversal detected"]

    # Try active first
    try:
        if os.path.isfile(active_path):
            with open(active_path, encoding="utf-8") as f:
                return json.load(f), []
    except (OSError, json.JSONDecodeError) as e:
        return None, [f"error reading active deck: {e}"]

    # Try archived
    archived_dir = _archived_dir()
    if archived_dir is not None:
        archived_path = os.path.join(archived_dir, f"{deck_id}.json")
        if not _is_path_jailed(archived_path):
            return None, ["path traversal detected"]
        try:
            if os.path.isfile(archived_path):
                with open(archived_path, encoding="utf-8") as f:
                    return json.load(f), []
        except (OSError, json.JSONDecodeError) as e:
            return None, [f"error reading archived deck: {e}"]

    return None, [f"deck not found: {deck_id!r}"]


def archive_deck(deck_id: str) -> tuple[bool, list[str]]:
    """Move a deck from _decks_dir() to _archived_dir().

    Returns (True, []) on success, (False, [reason]) if not found in active
    or the move fails. Never raises.
    """
    if not deck_id or not isinstance(deck_id, str):
        return False, ["invalid deck_id"]

    decks_dir = _decks_dir()
    archived_dir = _archived_dir()
    if decks_dir is None or archived_dir is None:
        return False, ["no workspace available"]

    active_path = os.path.join(decks_dir, f"{deck_id}.json")
    if not _is_path_jailed(active_path):
        return False, ["path traversal detected"]

    try:
        if not os.path.isfile(active_path):
            return False, [f"deck not found in active decks: {deck_id!r}"]

        os.makedirs(archived_dir, exist_ok=True)
        archive_path = os.path.join(archived_dir, f"{deck_id}.json")
        if not _is_path_jailed(archive_path):
            return False, ["path traversal detected"]

        problems = _move_preserving(active_path, archive_path, "failed to archive deck")
        return (not problems), problems
    except (OSError, shutil.Error) as e:
        return False, [f"failed to archive deck: {e}"]


def delete_deck(deck_id: str) -> tuple[bool, list[str]]:
    """Move a deck (from wherever it is) to _System/Archive/SmartDecks/.

    Returns (True, []) on success, (False, [reason]) if the deck isn't found
    anywhere. Never raises.
    """
    if not deck_id or not isinstance(deck_id, str):
        return False, ["invalid deck_id"]

    decks_dir = _decks_dir()
    if decks_dir is None:
        return False, ["no workspace available"]

    # Check active directory
    active_path = os.path.join(decks_dir, f"{deck_id}.json")
    if not _is_path_jailed(active_path):
        return False, ["path traversal detected"]

    source_path = None
    if os.path.isfile(active_path):
        source_path = active_path
    else:
        # Check archived directory
        archived_dir = _archived_dir()
        if archived_dir is not None:
            archived_path = os.path.join(archived_dir, f"{deck_id}.json")
            if not _is_path_jailed(archived_path):
                return False, ["path traversal detected"]
            if os.path.isfile(archived_path):
                source_path = archived_path

    if source_path is None:
        return False, [f"deck not found anywhere: {deck_id!r}"]

    try:
        # Get the system Archive folder
        delete_dir = _deleted_dir()
        if delete_dir is None:
            return False, ["no workspace available"]

        os.makedirs(delete_dir, exist_ok=True)

        # Verify destination is jailed (relative to Archive, which is itself
        # under _System -- this is already safe but check for safety)
        dest_path = os.path.join(delete_dir, f"{deck_id}.json")
        if not workspace.path_within_workspace(dest_path):
            return False, ["destination path is outside workspace"]

        problems = _move_preserving(source_path, dest_path, "failed to delete deck")
        return (not problems), problems
    except (OSError, shutil.Error) as e:
        return False, [f"failed to delete deck: {e}"]


def list_templates(kind: str) -> list[dict]:
    """List templates by kind: 'deck' or 'slide'.

    Scans *.json files in Library/SmartDecks/'Deck Templates' or
    Library/SmartDecks/'Slide Templates' respectively. Returns [{name, path}]
    sorted by name, or [] if the workspace/folder is missing or kind is invalid.
    Never raises -- unreadable/malformed files are just skipped.
    """
    if kind == "deck":
        folder_name = "Deck Templates"
    elif kind == "slide":
        folder_name = "Slide Templates"
    else:
        return []

    smartdecks_base = _smartdecks_base()
    if not smartdecks_base:
        return []

    template_dir = os.path.join(smartdecks_base, folder_name)
    if not os.path.isdir(template_dir):
        return []

    templates = []
    for filepath in glob.glob(os.path.join(template_dir, "*.json")):
        try:
            filename = os.path.basename(filepath)
            # Store just the name without the .json extension
            name = filename[:-5] if filename.endswith(".json") else filename
            templates.append({
                "name": name,
                "path": filepath,
            })
        except Exception:
            # Skip unreadable or malformed files
            continue

    return sorted(templates, key=lambda x: x["name"])
