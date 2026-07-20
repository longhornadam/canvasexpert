"""End-to-end differentiation demo.

Pushes the 3 CS tier quizzes and assigns each to a DIFFERENT third of the
roster via assignment overrides -> "only some kids get this one."

Quizzes are left UNPUBLISHED (safe: students can't see them), but the
"Assign to" panel will show each tier targeting a different student set.

Run: py push_tiers.py
   or, to push an arbitrary set of variants instead of the CS-tiers demo:
       py push_tiers.py --manifest <path-to-manifest.json>
   where the manifest is a JSON array of objects, each with:
     "label"       - display name (required)
     "path"        - file path to the QuizForge .txt (required)
     "student_ids" - list of Canvas user IDs for the assignment override (optional)
     "group_name"  - display name of the Canvas group, for logging (optional)

   When "student_ids" is provided for every entry the roster-fetch + chunk step
   is skipped entirely (the IDs came from Canvas group memberships resolved by
   the web UI). When any entry is missing "student_ids" the full roster is
   fetched and split into N equal contiguous groups as before.
"""
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from api import canvas, qf_pusher
from api.canvas import COURSE_ID

FOLDER = os.path.join("qf_materials", "qf quiz examples")
TIERS = [
    ("Tier 1", "cs_loops_checkpoint_tier1.txt"),
    ("Tier 2", "cs_loops_checkpoint_tier2.txt"),
    ("Tier 3", "cs_loops_checkpoint_tier3.txt"),
]
STATE_PATH = ".experiment_state.json"


def load_manifest(path):
    """Return the raw list of manifest entry dicts from a JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_students():
    status, data = canvas.get(
        canvas.core(f"/courses/{COURSE_ID}/enrollments"),
        params={"type[]": "StudentEnrollment", "per_page": 100},
    )
    return [{"name": e["user"]["name"], "user_id": e["user_id"]}
            for e in data if e.get("type") == "StudentEnrollment"]


def chunk(lst, n):
    """Split lst into n roughly equal contiguous groups."""
    k, r = divmod(len(lst), n)
    out, i = [], 0
    for g in range(n):
        size = k + (1 if g < r else 0)
        out.append(lst[i:i + size])
        i += size
    return out


def record_override(rec):
    state = {"quizzes": [], "overrides": [], "files": []}
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            state = json.load(f)
    state.setdefault("overrides", []).append(rec)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def main():
    if "--manifest" in sys.argv:
        manifest_path = sys.argv[sys.argv.index("--manifest") + 1]
        entries = load_manifest(manifest_path)
    else:
        entries = [{"label": label, "path": os.path.join(FOLDER, fname)}
                   for label, fname in TIERS]

    # If every entry carries pre-resolved student_ids (supplied by the web UI
    # from Canvas group memberships), skip the roster-fetch + chunk entirely.
    ids_provided = all(e.get("student_ids") for e in entries)

    if ids_provided:
        print(f"\nUsing group-based student_ids from manifest ({len(entries)} groups)")
        for e in entries:
            grp_name = e.get("group_name", e["label"])
            print(f"  {e['label']} -> {grp_name}: {len(e['student_ids'])} students")
        student_id_lists = [e["student_ids"] for e in entries]
    else:
        students = get_students()
        print(f"\nRoster: {len(students)} students (splitting into {len(entries)} groups)")
        groups = chunk(students, len(entries))
        for e, grp in zip(entries, groups):
            names = ", ".join(s["name"] for s in grp)
            print(f"  {e['label']}: {len(grp)} students -> {names}")
        student_id_lists = [[s["user_id"] for s in grp] for grp in groups]

    for entry, student_ids in zip(entries, student_id_lists):
        label = entry["label"]
        path  = entry["path"]
        print("\n" + "=" * 70)
        print(f"{label} -> {path}")
        print("=" * 70)
        rec = qf_pusher.push_file(path)
        if not rec:
            print(f"  !! {label} push failed, skipping override")
            continue

        aid = rec["assignment_id"]

        # The web UI may pre-split a tier into one standard override plus dated
        # extra-time overrides (see _expand_variants_extra_time). Fall back to a
        # single group override when no `overrides` list is present.
        ov_specs = entry.get("overrides") or [
            {"student_ids": student_ids, "title": f"{label} group"}]

        any_ok = False
        for spec in ov_specs:
            body = {"student_ids": spec["student_ids"],
                    "title": spec.get("title", f"{label} group")}
            for k in ("due_at", "unlock_at", "lock_at"):
                if spec.get(k):
                    body[k] = spec[k]
            extra = f", due {spec['due_at']}" if spec.get("due_at") else ""
            print(f"\n  [override] {body['title']}: {len(spec['student_ids'])} students{extra}")
            status, ovr = canvas.post(
                canvas.core(f"/courses/{COURSE_ID}/assignments/{aid}/overrides"),
                json={"assignment_override": body},
            )
            if isinstance(ovr, dict) and "id" in ovr:
                record_override({"assignment_id": aid, "override_id": ovr["id"],
                                 "label": body["title"]})
                print(f"  [override] OK id={ovr['id']}")
                any_ok = True
            else:
                print(f"  [override] FAILED status={status}")

        if any_ok:
            # Restrict visibility to ONLY the override groups — removes the
            # "Everyone else" assignee so this tier is truly group-only.
            vstatus, _ = canvas.put(
                canvas.core(f"/courses/{COURSE_ID}/assignments/{aid}"),
                json={"assignment": {"only_visible_to_overrides": True}},
            )
            if vstatus in (200, 201):
                print("  [override] visibility restricted to group only")
            else:
                print(f"  [override] WARN visibility PATCH status={vstatus} "
                      "(quiz may still show to 'Everyone else')")

    print("\n" + "=" * 70)
    print("DONE. Each tier quiz now targets a different student group.")
    print("Validate in the UI: open each quiz's 'Assign to' / edit panel.")
    print("=" * 70)


if __name__ == "__main__":
    main()
