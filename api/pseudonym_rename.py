"""Carrying a pseudonym rename through the stores that keep one on disk.

The Identity Vault is the source of truth for a student's fake name, and it is
keyed by canvas_id, so renaming inside the vault is just a field update. Two
durable stores hold a pseudonym outside it, and each needs the opposite thing
done at a different moment:

* **Assessment history** (`api/dataforge/`) keys a snapshot row by canvas_id and
  resolves the label at read, so a rename needs nothing at all. That is only
  true for rows that actually carry the id. `backfill_assessment_history` adds
  it to any row written before that existed, and it has to run **before** the
  rename lands, because it resolves each row's stored pseudonym through the
  vault. Once a rename is applied the old pseudonym is gone from the vault
  entirely, and those rows can no longer be linked automatically.

* **Writing evidence** (`api/dailywriting/`) stores the pseudonym inside the
  student's prose on purpose. That module measured and rejected redacting a
  name out of stored writing, because a record with holes punched through it
  cannot show how a writer is developing. So the text keeps a readable name and
  `rewrite_writing_spans` swaps old for new **after** the rename, wherever it
  landed, including inside another student's span that named this student as a
  classmate.

Both are deliberately tolerant of a feature the teacher has never set up: a
rename must not fail because DataForge has no history folder or because no
writing has been ingested. A real failure is a different matter and is
reported, because a rename whose follow-through half-happened leaves a retired
pseudonym sitting in stored text, which is the exact thing a rename is
sometimes performed to retire.
"""
from __future__ import annotations

from pathlib import Path

from api import operational_log
from api.platform_services import workspace


def current_pseudonym(vault, canvas_id: str) -> str:
    """The pseudonym the vault currently holds for this student, or "".

    Read by scanning entries rather than through `get_or_assign`, which would
    mint a pseudonym for an id the vault does not know. A caller asking what
    the old name was must not create one as a side effect.
    """
    wanted = str(canvas_id or "").strip()
    if not wanted:
        return ""
    for entry in vault.entries():
        if str(entry.get("canvas_id") or "").strip() == wanted:
            return str(entry.get("pseudonym") or "").strip()
    return ""


def backfill_assessment_history() -> str:
    """Give every assessment history row a stable canvas_id. Call before a rename.

    Returns "" when there was nothing to do or the work succeeded, or a
    teacher-readable message when history exists but could not be updated. An
    unconfigured workspace, a missing history folder, and an unavailable vault
    are all "nothing to do": the teacher simply has no assessment history yet.
    """
    # Imported here, not at module scope: this module is reached from the WebUI
    # routes, and both packages pull in the workspace and the vault themselves.
    from api.dataforge import paths as dataforge_paths
    from api.dataforge.identity import (
        IdentityMigrationError,
        VaultIdentity,
        backfill_canvas_ids,
    )

    try:
        # ensure=False: a rename reads and rewrites existing history, so it must
        # never bring a DataForge workspace into being as a side effect. With
        # ensure=True this created the folders on a machine that has never
        # opened Assessments.
        paths = dataforge_paths.get_paths(ensure=False)
    except (IdentityMigrationError, OSError, RuntimeError):
        return ""
    if not Path(paths.history_dir).is_dir():
        return ""

    try:
        identity = VaultIdentity.from_paths(paths)
    except (IdentityMigrationError, OSError, RuntimeError):
        return ""

    try:
        backfill_canvas_ids(paths, identity.canvas_id_map())
    except IdentityMigrationError as exc:
        return (
            "The rename was not applied: this student's assessment history "
            f"could not be prepared for it first ({exc}). Nothing was changed."
        )
    except OSError:
        return ""
    return ""


def refresh_published_profile() -> str:
    """Rebuild the published standards profile, or remove it if it cannot be.

    The profile is a materialized artifact in the For AI zone, so unlike the
    history it is built from, it keeps whatever pseudonym it was written with
    until something rewrites it. Left alone after a rename it would keep
    handing an assistant a name the vault has retired, which in the case a
    rename exists to handle is the one name that must stop being served.

    Rebuilding is cheap because snapshots carry a stable canvas_id and resolve
    the current pseudonym at read. If it cannot be rebuilt, the stale file is
    removed instead: `get_standards_profile` then reports that the profile
    needs generating, which is honest, where serving a retired pseudonym is
    not. Returns "" unless the stale file could not even be removed.
    """
    from api.dataforge import paths as dataforge_paths, profile_export
    from api.dataforge.identity import IdentityMigrationError, VaultIdentity

    try:
        published = Path(workspace.for_ai_root()) / "DataForge" / profile_export.PROFILE_FILENAME
    except (OSError, RuntimeError, TypeError):
        return ""
    if not published.exists():
        # Nothing has been published, so there is no stale copy to worry about.
        return ""

    try:
        # ensure=False for the same reason as the backfill: rebuilding a profile
        # that already exists must not create workspace folders on the way.
        paths = dataforge_paths.get_paths(ensure=False)
        identity = VaultIdentity.from_paths(paths)
        profile_export.publish_profile(paths, anonymizer=identity)
        return ""
    except (IdentityMigrationError, profile_export.SharedPublishError, OSError, RuntimeError) as exc:
        operational_log.emit("pseudonym.profile_republish", "failed", error_class=type(exc))

    try:
        published.unlink()
    except OSError as exc:
        return (
            "The new name was saved, but the published standards profile still "
            f"refers to the old one and could not be updated or removed ({exc}). "
            "Delete it by hand before sharing the profile with an assistant."
        )
    return ""


def rewrite_writing_spans(old_pseudonym: str, new_pseudonym: str) -> str:
    """Rewrite a retired pseudonym to the new one across stored writing.

    Call after the vault records the rename. Returns "" on success or when
    there is no writing store yet, or a teacher-readable message naming both
    pseudonyms if the rewrite failed, so it can be retried: the rewrite is
    idempotent, and until it succeeds the old pseudonym is still sitting in
    stored text.
    """
    old = str(old_pseudonym or "").strip()
    new = str(new_pseudonym or "").strip()
    if not old or not new or old == new:
        return ""

    from api.dailywriting.cli.rewrite_pseudonym import rewrite_pseudonym
    from api.dailywriting.store.repo import (
        Repository,
        StoreError,
        workspace_store_root,
    )

    try:
        store_root = workspace_store_root()
    except StoreError:
        return ""
    if not store_root.is_dir():
        # Nothing has been ingested, so there is no stored span to rewrite, and
        # building a Repository here would be actively harmful: it resolves the
        # real vault through api/powergrader/context.py, whose no-workspace
        # fallback creates "_System/Identity Vault" under the current working
        # directory.
        return ""

    try:
        repository = Repository.default()
    except (StoreError, OSError, RuntimeError):
        return ""

    try:
        rewrite_pseudonym(repository, old_pseudonym=old, new_pseudonym=new)
    except (OSError, ValueError) as exc:
        return (
            f"The new name '{new}' was saved, but this student's stored writing "
            f"still refers to them as '{old}' ({exc}). Retry the rename to "
            "finish updating it."
        )
    return ""
