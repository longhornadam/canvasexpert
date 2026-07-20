"""Validate QuizForge_Base-compliant fixtures.

Doubles as the first stage of the future pusher: extract the JSON from the
<QUIZFORGE_JSON> envelope, parse it, and sanity-check QF compliance
(per-item rationales, required fields, type coverage).

Run: py validate_qf.py
"""
import glob
import json
import os
import re

FOLDER = os.path.join("qf_materials", "qf quiz examples")

ALL_TYPES = {"STIMULUS", "STIMULUS_END", "MC", "MA", "TF", "MATCHING", "FITB",
             "ESSAY", "FILEUPLOAD", "ORDERING", "CATEGORIZATION", "NUMERICAL"}
SCORED_SINGLE_RATIONALE = {"TF", "FITB", "MATCHING", "ORDERING", "NUMERICAL", "CATEGORIZATION"}
PER_CHOICE_RATIONALE = {"MC", "MA"}
NO_RATIONALE = {"ESSAY", "FILEUPLOAD", "STIMULUS", "STIMULUS_END"}

ENVELOPE = re.compile(r"<QUIZFORGE_JSON>(.*?)</QUIZFORGE_JSON>", re.DOTALL)


def extract_json(text):
    m = ENVELOPE.search(text)
    return m.group(1).strip() if m else None


def validate(path, seen_types):
    name = os.path.basename(path)
    with open(path, encoding="utf-8") as f:
        raw = f.read()

    payload = extract_json(raw)
    if payload is None:
        return [f"{name}: no <QUIZFORGE_JSON> envelope found"]
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        return [f"{name}: INVALID JSON - {e}"]

    problems = []
    items = data.get("items", [])
    rationale_ids = set()
    for r in data.get("rationales", []):
        rationale_ids.add(r.get("item_id"))

    for it in items:
        t = it.get("type")
        seen_types.add(t)
        if t not in ALL_TYPES:
            problems.append(f"{name}: unknown type {t!r}")
            continue
        iid = it.get("id")
        # rationale expectations
        if t in PER_CHOICE_RATIONALE or t in SCORED_SINGLE_RATIONALE:
            if iid not in rationale_ids:
                problems.append(f"{name}: scored item {iid!r} ({t}) missing rationale")
        # MC exactly one correct; MA at least two correct
        if t == "MC":
            n = sum(1 for c in it.get("choices", []) if c.get("correct"))
            if n != 1:
                problems.append(f"{name}: MC {iid!r} has {n} correct (need 1)")
        if t == "MA":
            n = sum(1 for c in it.get("choices", []) if c.get("correct"))
            if n < 2:
                problems.append(f"{name}: MA {iid!r} has {n} correct (need >=2)")

    title = data.get("title", "(untitled)")
    grp = data.get("metadata", {}).get("variant_group", "-")
    label = data.get("metadata", {}).get("variant_label", "-")
    type_counts = {}
    for it in items:
        type_counts[it["type"]] = type_counts.get(it["type"], 0) + 1
    summary = ", ".join(f"{k}x{v}" for k, v in sorted(type_counts.items()))
    print(f"  OK  {name}")
    print(f"       title: {title}")
    print(f"       group: {grp}  |  variant: {label}")
    print(f"       items: {summary}")
    return problems


def main():
    paths = sorted(glob.glob(os.path.join(FOLDER, "*.txt")))
    if not paths:
        print(f"No .txt fixtures found in {FOLDER}")
        return
    print(f"Validating {len(paths)} fixture(s) in {FOLDER}\n")
    seen_types = set()
    all_problems = []
    for p in paths:
        all_problems += validate(p, seen_types)
        print()

    print("=" * 60)
    missing = ALL_TYPES - seen_types
    print(f"Type coverage: {len(seen_types)}/{len(ALL_TYPES)} types present")
    if missing:
        print(f"  MISSING types across all fixtures: {sorted(missing)}")
    else:
        print("  All 12 QuizForge types are represented across the set.")
    print()
    if all_problems:
        print(f"COMPLIANCE ISSUES ({len(all_problems)}):")
        for p in all_problems:
            print(f"  - {p}")
    else:
        print("No compliance issues found.")


if __name__ == "__main__":
    main()
