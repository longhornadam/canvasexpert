"""Identity Vault boundary for the DataForge merge.

The legacy DataForge CSV is read only during the one-time migration.  All live
DataForge identity work after that goes through CanvasExpert's existing Vault.
"""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path

from api.feedback_vault import Vault
from api.webui import workspace


class IdentityMigrationError(ValueError):
    """Migration cannot proceed without risking identity loss or guessing."""


def vault_path() -> Path:
    directory = workspace.identity_vault_dir()
    if not directory:
        raise IdentityMigrationError("CanvasExpert Identity Vault is not configured.")
    return Path(directory) / "vault.json"


def load_legacy_links(path: Path) -> dict[str, str]:
    """Read only linked ``anon_name -> real_id`` rows from the old CSV."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            required = {"anon_name", "real_id"}
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                raise IdentityMigrationError("The legacy identity map has an unsupported header.")
            links = {}
            ids = {}
            for row in reader:
                old_name = str(row.get("anon_name") or "").strip()
                real_id = str(row.get("real_id") or "").strip()
                if not old_name or not real_id:
                    continue
                if old_name in links and links[old_name] != real_id:
                    raise IdentityMigrationError(f"Legacy pseudonym {old_name} has conflicting IDs.")
                if real_id in ids and ids[real_id] != old_name:
                    raise IdentityMigrationError(f"Legacy ID {real_id} has conflicting pseudonyms.")
                links[old_name] = real_id
                ids[real_id] = old_name
            return links
    except IdentityMigrationError:
        raise
    except (OSError, csv.Error) as exc:
        raise IdentityMigrationError(f"Could not read the legacy identity map: {exc}") from exc


def build_rekey_plan(legacy_links: dict[str, str], vault_entries: list[dict]) -> dict:
    """Resolve legacy linked students against exactly one Vault SIS entry."""
    by_sis = {}
    for entry in vault_entries or []:
        if not isinstance(entry, dict):
            continue
        sis_id = str(entry.get("sis_id") or "").strip()
        pseudonym = str(entry.get("pseudonym") or "").strip()
        if not sis_id:
            continue
        by_sis.setdefault(sis_id, []).append(entry)

    rekey = {}
    unmatched = []
    ambiguous = []
    for old_name, sis_id in sorted((legacy_links or {}).items()):
        candidates = by_sis.get(str(sis_id).strip(), [])
        if len(candidates) == 1 and str(candidates[0].get("pseudonym") or "").strip():
            rekey[old_name] = str(candidates[0]["pseudonym"]).strip()
        elif len(candidates) > 1:
            ambiguous.append(old_name)
        else:
            unmatched.append(old_name)
    if ambiguous:
        raise IdentityMigrationError(
            "Cannot migrate ambiguous legacy identities: " + ", ".join(ambiguous)
        )
    return {"rekey": rekey, "unmatched": unmatched}


def _migrate_snapshot(snapshot: dict, rekey: dict[str, str]) -> tuple[dict, int, int]:
    updated = json.loads(json.dumps(snapshot))
    migrated = 0
    anonymous = 0
    students = updated.get("students") or []
    if not isinstance(students, list):
        raise IdentityMigrationError("A history snapshot has an invalid students list.")
    for student in students:
        if not isinstance(student, dict):
            raise IdentityMigrationError("A history snapshot contains an invalid student row.")
        old_name = str(student.get("n") or "").strip()
        if old_name and old_name in rekey:
            student["n"] = rekey[old_name]
            student["identity_state"] = "identity_vault"
            migrated += 1
        elif old_name:
            # Scores remain useful for aggregate reporting, but the legacy key
            # must not survive into the one-pseudonym-space state.
            student["n"] = ""
            student["identity_state"] = "anonymous_aggregate"
            anonymous += 1
        elif student.get("identity_state") != "identity_vault":
            student["identity_state"] = "anonymous_aggregate"
    updated["identity_format"] = "identity_vault.v1"
    return updated, migrated, anonymous


def migrate_snapshots(paths, rekey: dict[str, str]) -> dict:
    """Validate and atomically stage every snapshot before replacing any file."""
    staged = []
    migrated = 0
    anonymous = 0
    for source in sorted(Path(paths.history_dir).glob("*.json")):
        try:
            snapshot = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(snapshot, dict):
                raise IdentityMigrationError(f"History snapshot {source.name} is not an object.")
            updated, changed, aggregate = _migrate_snapshot(snapshot, rekey)
            temporary = source.with_name(source.name + ".vault-migration.tmp")
            temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=0), encoding="utf-8")
            staged.append((source, temporary))
            migrated += changed
            anonymous += aggregate
        except IdentityMigrationError:
            for _, temporary in staged:
                temporary.unlink(missing_ok=True)
            raise
        except (OSError, json.JSONDecodeError) as exc:
            for _, temporary in staged:
                temporary.unlink(missing_ok=True)
            raise IdentityMigrationError(f"Could not stage {source.name}: {exc}") from exc
    try:
        for source, temporary in staged:
            os.replace(temporary, source)
    except OSError as exc:
        for _, temporary in staged:
            temporary.unlink(missing_ok=True)
        raise IdentityMigrationError(f"Could not complete history migration: {exc}") from exc
    return {"snapshots": len(staged), "migrated_students": migrated, "anonymous_students": anonymous}


def migrate_legacy_state(paths, *, vault: Vault | None = None) -> dict:
    """Migrate old links/snapshots once, then remove the old private map."""
    legacy = Path(paths.anon_map)
    if not legacy.exists():
        return {"migrated": False, "snapshots": 0, "migrated_students": 0, "anonymous_students": 0}
    vault = vault or Vault(str(vault_path()))
    links = load_legacy_links(legacy)
    plan = build_rekey_plan(links, vault.entries())
    report = migrate_snapshots(paths, plan["rekey"])
    for candidate in (legacy, legacy.with_name(legacy.name + ".bak")):
        candidate.unlink(missing_ok=True)
    return {"migrated": True, **report, "unmatched": plan["unmatched"]}


class VaultIdentity:
    """Parser-facing identity provider backed only by current Vault entries."""

    def __init__(self, vault: Vault):
        self.vault = vault
        self._entries = vault.entries()
        self._by_sis = {}
        self._by_name = {}
        for entry in self._entries:
            sis_id = str(entry.get("sis_id") or "").strip()
            pseudonym = str(entry.get("pseudonym") or "").strip()
            if sis_id and pseudonym:
                self._by_sis.setdefault(sis_id, []).append(entry)
            real_name = str(entry.get("real_name") or "").strip().casefold()
            if real_name and pseudonym:
                self._by_name.setdefault(real_name, []).append(entry)

    @classmethod
    def from_paths(cls, paths):
        return cls(Vault(str(vault_path())))

    def _entry_for_student(self, real_name: str, local_id: str) -> dict | None:
        candidates = self._by_sis.get(str(local_id or "").strip(), [])
        if len(candidates) == 1:
            return candidates[0]
        return None

    def map_student(self, real_name: str, local_id: str) -> tuple[str, str]:
        entry = self._entry_for_student(real_name, local_id)
        if not entry:
            return "", ""
        return str(entry.get("pseudonym") or ""), ""

    def map_name(self, real_name: str) -> str:
        candidates = self._by_name.get(str(real_name or "").strip().casefold(), [])
        return str(candidates[0].get("pseudonym") or "") if len(candidates) == 1 else ""

    def linked_students(self) -> dict[str, str]:
        out = {}
        for sis_id, entries in self._by_sis.items():
            if len(entries) == 1:
                out[str(entries[0].get("pseudonym") or "")] = sis_id
        return {key: value for key, value in out.items() if key}

    # Real IDs shorter than this are not treated as leaks. A 2-3 digit local ID
    # collides with ordinary report content (a raw score of 53, a scale score, a
    # percentage), and a false positive here blocks a legitimate run outright.
    _MIN_ID_LEAK_LEN = 4

    def detect_leaks(self, text: str) -> list[str]:
        """Real names or real IDs still present in `text`, case-insensitively.

        Deliberately not ``feedback_scrub.verify_clean``. That scan matches every
        whitespace token of a real name with no length floor, which is right for
        the feedback pipeline (scrub first, then treat any survivor as a bug to
        log) but wrong here: a vault name of "Ruiz, Ana J" makes the lone token
        "J" a leak, and DataForge's caller raises rather than logs, so any
        artifact with a standalone "J" or a score of "1" would fail a legitimate
        run closed. It also discards the vault's id set, and the Eduphoria Local
        ID is the join key that must never travel with the pseudonym-keyed
        profile.

        The name rules are a straight port of what the retired ``NameAnonymizer``
        shipped and had tests for. Known limit, inherited and deliberate: an
        artifact rendering a surname alone is not caught, because ordinary report
        text contains ordinary words and a false positive stops the teacher.
        """
        raw = str(text)
        names, ids = self.vault.all_real_identifiers()
        leaks: list[str] = []

        for name in names:
            if self._name_present(raw, name):
                leaks.append(name)

        for real_id in ids:
            token = str(real_id or "").strip()
            if len(token) < self._MIN_ID_LEAK_LEN:
                continue
            # Word-bounded, so an id does not match inside a longer number.
            if re.search(rf"(?<!\w){re.escape(token)}(?!\w)", raw, flags=re.IGNORECASE):
                leaks.append(token)

        return leaks

    @classmethod
    def _name_present(cls, text: str, real_name: str) -> bool:
        """Whether any plausible rendering of `real_name` survives in `text`.

        Eduphoria stores "Last, First". A report that renders "First Last" is
        still a leak, and an exact check on the stored form alone misses it.
        """
        cleaned = re.sub(r"\s+", " ", str(real_name or "")).strip()
        if not cleaned:
            return False

        haystack = text.lower()
        variants = {cleaned}
        if "," in cleaned:
            last, _, first = cleaned.partition(",")
            last, first = last.strip(), first.strip()
            if last and first:
                variants.add(f"{first} {last}")
        return any(variant.lower() in haystack for variant in variants)
