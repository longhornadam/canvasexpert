# Example custom routine — a read-only "missing work" nudge check.
# Copy this file to a name WITHOUT the leading underscore to activate it.
# No imports needed: routine, active_courses, canvas_get_all, datetime are injected.

@routine("missing_work",
         label="Missing-work nudge",
         writes=False,
         default={"enabled": False, "every_hours": 24, "params": {"min_missing": 3}})
def run(params):
    min_missing = int(params.get("min_missing", 3))
    today = datetime.now().date().isoformat()
    lines, ok, total = [], True, 0
    for c in active_courses():
        cid = str(c["id"])
        asgns, err = canvas_get_all(f"/api/v1/courses/{cid}/assignments", {"per_page": 100})
        if err:
            lines.append(f"\u2717 {c['nickname']}: {err}"); ok = False; continue
        due_ids = {str(a["id"]) for a in (asgns or [])
                   if (a.get("due_at") or "")[:10] and (a.get("due_at") or "")[:10] <= today}
        subs, err = canvas_get_all(f"/api/v1/courses/{cid}/students/submissions",
                                   {"student_ids[]": "all", "per_page": 100})
        if err:
            lines.append(f"\u2717 {c['nickname']}: {err}"); ok = False; continue
        missing = {}
        for s_ in (subs or []):
            if (str(s_.get("assignment_id")) in due_ids
                    and s_.get("workflow_state") == "unsubmitted"):
                missing[s_["user_id"]] = missing.get(s_["user_id"], 0) + 1
        flagged = [u for u, n in missing.items() if n >= min_missing]
        total += len(flagged)
        lines.append(
            f"\u2691 {c['nickname']}: {len(flagged)} student(s) with \u2265{min_missing} missing"
            if flagged else f"\u2713 {c['nickname']}: none at the threshold")
    return {"ok": ok, "lines": lines,
            "summary": f"{total} student(s) flagged across active courses"}