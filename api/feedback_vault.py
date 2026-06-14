"""Pseudonym vault — the real<->pseudonym map for FeedbackExpert.

The single most sensitive artifact in the app: it is the only thing that can
re-identify pseudonymized work. It lives in the synced workspace
(FeedbackExpert/_vault/), NEVER in the repo, and is NEVER transmitted anywhere.

Keyed on the Canvas user id (stable, present in the Student Analysis CSV `ID`
column), so a student keeps the same opaque pseudonym forever — across CSVs,
sources, and years. Pure stdlib; offline-testable.

Pseudonyms are opaque sequential tokens ("S001", "S002", ...) carrying no real
information; only this vault maps them back.
"""
import json
import os


class Vault:
    def __init__(self, path: str):
        self.path = path
        self._by_id = {}          # canvas_id(str) -> {pseudonym, real_name, sis_id, first_seen}
        self._by_pseudo = {}      # pseudonym -> canvas_id(str)
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self._by_id = data.get("by_canvas_id", {})
            self._by_pseudo = {v["pseudonym"]: cid for cid, v in self._by_id.items()}

    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"by_canvas_id": self._by_id}, f, indent=2)

    def _next_pseudonym(self) -> str:
        return f"S{len(self._by_id) + 1:03d}"

    def get_or_assign(self, canvas_id, real_name="", sis_id="") -> str:
        """Return the stable pseudonym for this student, assigning one on first sight.
        Backfills name/sis if they were unknown before. Does not auto-save."""
        cid = str(canvas_id)
        entry = self._by_id.get(cid)
        if entry is None:
            from datetime import datetime
            pseudo = self._next_pseudonym()
            entry = {"pseudonym": pseudo, "real_name": real_name, "sis_id": sis_id,
                     "first_seen": datetime.now().isoformat(timespec="seconds")}
            self._by_id[cid] = entry
            self._by_pseudo[pseudo] = cid
        else:
            if real_name and not entry.get("real_name"):
                entry["real_name"] = real_name
            if sis_id and not entry.get("sis_id"):
                entry["sis_id"] = sis_id
        return entry["pseudonym"]

    def reverse(self, pseudonym: str):
        """Pseudonym -> {canvas_id, real_name, sis_id} or None."""
        cid = self._by_pseudo.get(pseudonym)
        if cid is None:
            return None
        e = self._by_id[cid]
        return {"canvas_id": cid, "real_name": e.get("real_name", ""),
                "sis_id": e.get("sis_id", "")}

    def all_real_identifiers(self):
        """(names, ids) sets of every real identifier the vault knows — used by the
        outbound safety scan to detect any leak before transmission."""
        names, ids = set(), set()
        for cid, e in self._by_id.items():
            ids.add(str(cid))
            if e.get("sis_id"):
                ids.add(str(e["sis_id"]))
            if e.get("real_name"):
                names.add(e["real_name"])
        return names, ids

    def __len__(self):
        return len(self._by_id)
