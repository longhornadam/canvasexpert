"""Pseudonym vault v2 — the real<->pseudonym map for feedback tools.

The single most sensitive artifact in the app: it is the only thing that can
re-identify pseudonymized work. It lives in the synced workspace
(`_System/Identity Vault/`), NEVER in the repo, and is NEVER transmitted
anywhere.

Keyed on the Canvas user id (stable, present in the Student Analysis CSV `ID`
column), so a student keeps the same opaque pseudonym forever — across CSVs,
sources, and years.

v2 pseudonyms are realistic fake names like "Sparky McGee" drawn from a pool
disjoint from real rosters. Pure stdlib; offline-testable.
"""
import json
import os
import random
from contextlib import contextmanager
from pathlib import Path

from api.storage_support import atomic_write_json, interprocess_lock

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_name_pool(filename: str) -> list[str]:
    path = os.path.join(_MODULE_DIR, "data", filename)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


_FAST_FIRST = _load_name_pool("fake_first_names.txt")
_FAST_LAST = _load_name_pool("fake_last_names.txt")


class Vault:
    def __init__(self, path: str):
        self.path = path
        self._by_id = {}          # canvas_id(str) -> {pseudonym, pseudo_first, pseudo_last,
                                  #                   real_name, sis_id, nicknames, first_seen}
        self._by_pseudo = {}      # pseudonym -> canvas_id(str)
        self._load()

    def _load(self):
        data = {}
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        self._apply_document(data)

    def _apply_document(self, data: dict):
        """Replace in-memory maps with one freshly loaded document."""
        raw_entries = data.get("by_canvas_id", {}) if isinstance(data, dict) else {}
        self._by_id = raw_entries if isinstance(raw_entries, dict) else {}
        self._by_pseudo = {
            v["pseudonym"]: cid
            for cid, v in self._by_id.items()
            if isinstance(v, dict) and v.get("pseudonym")
        }
        # Upgrade legacy entries: fill missing v2 fields
        for cid, entry in self._by_id.items():
            changed = False
            if "pseudo_first" not in entry:
                entry["pseudo_first"] = ""
                changed = True
            if "pseudo_last" not in entry:
                entry["pseudo_last"] = ""
                changed = True
            if "nicknames" not in entry:
                entry["nicknames"] = []
                changed = True
            # Upgrade S001-style pseudonyms to fake names
            if entry.get("pseudonym", "").startswith("S0") and not entry.get("pseudo_first"):
                old_pseudo = entry["pseudonym"]
                self._assign_fake_name(entry, set(), set())
                self._by_pseudo.pop(old_pseudo, None)
                self._by_pseudo[entry["pseudonym"]] = cid
                changed = True
            if changed:
                self._by_id[cid] = entry

    def _lock_path(self) -> Path:
        path = Path(self.path)
        return path.with_name(path.name + ".lock")

    def _save_unlocked(self):
        atomic_write_json(Path(self.path), {"by_canvas_id": self._by_id})

    @contextmanager
    def transaction(self):
        """Reload, mutate, and atomically save this vault under one lock."""
        with interprocess_lock(self._lock_path()):
            self._load()
            try:
                yield self
            except Exception:
                raise
            else:
                self._save_unlocked()

    def save(self):
        with interprocess_lock(self._lock_path()):
            self._save_unlocked()

    def _existing_tokens(self, roster_names: set | None = None) -> tuple[set, set]:
        """Return (used_fake_firsts, used_fake_lasts) from the vault + roster."""
        used_first: set = set()
        used_last: set = set()
        for cid, entry in self._by_id.items():
            if entry.get("pseudo_first"):
                used_first.add(entry["pseudo_first"].lower())
            if entry.get("pseudo_last"):
                used_last.add(entry["pseudo_last"].lower())
        if roster_names:
            for n in roster_names:
                tokens = n.strip().lower().split()
                for t in tokens:
                    # A roster token blocks both first and last pools
                    used_first.add(t)
                    used_last.add(t)
        return used_first, used_last

    def _assign_fake_name(self, entry: dict, used_first: set, used_last: set,
                          roster_tokens: set | None = None):
        """Pick (first, last) from the pool, collision-checked against used tokens
        and the combined roster-token + vault set. Mutates entry in-place."""
        # Build the full set of tokens that must not match a fake name
        banned = set(used_first) | set(used_last)
        if roster_tokens:
            banned |= {t.lower() for t in roster_tokens}

        pool_first = [n for n in _FAST_FIRST if n.lower() not in banned]
        pool_last = [n for n in _FAST_LAST if n.lower() not in banned]

        if not pool_first:
            # Fallback: pick any fake first, append a number
            first = _FAST_FIRST[0] if _FAST_FIRST else "Student"
            suffix = 1
            while f"{first.lower()}{suffix}" in banned:
                suffix += 1
            first = f"{first}{suffix}"
        else:
            first = random.choice(pool_first)

        if not pool_last:
            last = _FAST_LAST[0] if _FAST_LAST else "Person"
            suffix = 1
            while f"{last.lower()}{suffix}" in banned:
                suffix += 1
            last = f"{last}{suffix}"
        else:
            last = random.choice(pool_last)

        entry["pseudo_first"] = first
        entry["pseudo_last"] = last
        entry["pseudonym"] = f"{first} {last}"

    def get_or_assign(self, canvas_id, real_name="", sis_id="",
                      roster_names: set | None = None) -> str:
        """Return the stable pseudonym for this student, assigning one on first sight.
        Backfills name/sis if they were unknown before. If `roster_names` is provided,
        the fake name will avoid colliding with any real roster token.
        Does not auto-save."""
        cid = str(canvas_id)
        entry = self._by_id.get(cid)
        if entry is None:
            from datetime import datetime
            used_first, used_last = self._existing_tokens(roster_names)
            pseudo_first = ""
            pseudo_last = ""
            pseudonym = ""
            # Pick a fake name
            used_fake_tokens = set()
            if roster_names:
                for n in roster_names:
                    used_fake_tokens.update(t.lower() for t in n.split())
            entry_pseudo = {}
            self._assign_fake_name(entry_pseudo, used_first, used_last,
                                   roster_tokens=used_fake_tokens)
            pseudo_first = entry_pseudo["pseudo_first"]
            pseudo_last = entry_pseudo["pseudo_last"]
            pseudonym = entry_pseudo["pseudonym"]

            entry = {
                "pseudonym": pseudonym,
                "pseudo_first": pseudo_first,
                "pseudo_last": pseudo_last,
                "real_name": real_name,
                "sis_id": sis_id,
                "nicknames": [],
                "first_seen": datetime.now().isoformat(timespec="seconds"),
            }
            self._by_id[cid] = entry
            self._by_pseudo[pseudonym] = cid
        else:
            if real_name and not entry.get("real_name"):
                entry["real_name"] = real_name
            if sis_id and not entry.get("sis_id"):
                entry["sis_id"] = sis_id
        return entry["pseudonym"]

    def set_nicknames(self, canvas_id, nicknames: list[str]):
        """Set the nicknames for a student (dedup case-insensitively, strip, no empty strings).
        Caller must call save()."""
        cid = str(canvas_id)
        entry = self._by_id.get(cid)
        if entry is None:
            return
        seen: set = set()
        clean = []
        for n in nicknames:
            n_stripped = n.strip()
            if n_stripped and n_stripped.lower() not in seen:
                seen.add(n_stripped.lower())
                clean.append(n_stripped)
        entry["nicknames"] = sorted(clean)

    def add_nicknames(self, canvas_id, nicknames: list[str]):
        """Merge nicknames into the existing set (dedup case-insensitively, strip,
        no empty strings) — does NOT clobber teacher-entered ones. Caller saves."""
        cid = str(canvas_id)
        entry = self._by_id.get(cid)
        if entry is None:
            return
        existing = entry.get("nicknames", [])
        seen = {n.lower() for n in existing}
        merged = list(existing)
        for n in nicknames:
            ns = n.strip()
            if ns and ns.lower() not in seen:
                seen.add(ns.lower())
                merged.append(ns)
        entry["nicknames"] = sorted(merged)

    def set_pseudonym(self, canvas_id, first: str, last: str):
        """Manual override from the UI. Caller must call save()."""
        cid = str(canvas_id)
        entry = self._by_id.get(cid)
        if entry is None:
            return
        old_pseudo = entry.get("pseudonym", "")
        entry["pseudo_first"] = first.strip()
        entry["pseudo_last"] = last.strip()
        entry["pseudonym"] = f"{first.strip()} {last.strip()}"
        self._by_pseudo.pop(old_pseudo, None)
        self._by_pseudo[entry["pseudonym"]] = cid

    def regenerate_pseudonym(self, canvas_id, roster_names: set | None = None):
        """Assign a new fake name, collision-checked. Caller must call save()."""
        cid = str(canvas_id)
        entry = self._by_id.get(cid)
        if entry is None:
            return
        old_pseudo = entry.get("pseudonym", "")
        used_first, used_last = self._existing_tokens(roster_names)
        # Temporarily remove self from the used sets
        old_first = entry.get("pseudo_first", "").lower()
        old_last = entry.get("pseudo_last", "").lower()
        used_first.discard(old_first)
        used_last.discard(old_last)

        used_fake_tokens = set()
        if roster_names:
            for n in roster_names:
                used_fake_tokens.update(t.lower() for t in n.split())

        fresh = {}
        self._assign_fake_name(fresh, used_first, used_last,
                               roster_tokens=used_fake_tokens)
        # If we happened to get the same one, try again
        if fresh["pseudonym"] == old_pseudo:
            used_first.add(fresh["pseudo_first"].lower())
            fresh = {}
            self._assign_fake_name(fresh, used_first, used_last,
                                   roster_tokens=used_fake_tokens)

        entry["pseudo_first"] = fresh["pseudo_first"]
        entry["pseudo_last"] = fresh["pseudo_last"]
        entry["pseudonym"] = fresh["pseudonym"]
        self._by_pseudo.pop(old_pseudo, None)
        self._by_pseudo[entry["pseudonym"]] = cid

    def reverse(self, pseudonym: str):
        """Pseudonym -> {canvas_id, real_name, sis_id} or None."""
        cid = self._by_pseudo.get(pseudonym)
        if cid is None:
            return None
        e = self._by_id[cid]
        return {"canvas_id": cid, "real_name": e.get("real_name", ""),
                "sis_id": e.get("sis_id", "")}

    def entries(self) -> list[dict]:
        """Return all entries as a list for the UI table."""
        result = []
        for cid, e in self._by_id.items():
            result.append({
                "canvas_id": cid,
                "real_name": e.get("real_name", ""),
                "sis_id": e.get("sis_id", ""),
                "pseudonym": e.get("pseudonym", ""),
                "pseudo_first": e.get("pseudo_first", ""),
                "pseudo_last": e.get("pseudo_last", ""),
                "nicknames": e.get("nicknames", []),
                "first_seen": e.get("first_seen", ""),
            })
        # Sort by real_name for the UI
        result.sort(key=lambda x: x["real_name"].lower())
        return result

    def all_real_identifiers(self):
        """(names, ids) sets of every real identifier the vault knows — used by the
        outbound safety scan to detect any leak before transmission.
        Now includes nicknames."""
        names, ids = set(), set()
        for cid, e in self._by_id.items():
            ids.add(str(cid))
            if e.get("sis_id"):
                ids.add(str(e["sis_id"]))
            if e.get("real_name"):
                names.add(e["real_name"])
            for nn in e.get("nicknames", []):
                if nn:
                    names.add(nn)
        return names, ids

    def __len__(self):
        return len(self._by_id)
