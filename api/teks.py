"""TEKS handling for the QuizForge -> Canvas pipeline.

QF carries TEKS per item as `metadata.teks` (a code string or list of codes).

Per-question Canvas Outcome alignment is UI-only (the New Quizzes items API has
no alignment field), so we do NOT create Outcomes/rubrics. Instead:
  - Tracking: read the codes, print a coverage report (teacher-side).
  - Labeling: embed a small visible "TEKS: ..." tag in each tagged question so
    the standard shows at a glance in the quiz.
"""


def item_teks(qf_item):
    """Normalize an item's TEKS metadata to a list of codes."""
    md = qf_item.get("metadata") or {}
    t = md.get("teks")
    if not t:
        return []
    return [t] if isinstance(t, str) else list(t)


def collect(items):
    """Return (ordered unique codes, {code: [item_ids]})."""
    order, by_code = [], {}
    for it in items:
        for code in item_teks(it):
            if code not in by_code:
                by_code[code] = []
                order.append(code)
            by_code[code].append(it.get("id"))
    return order, by_code


def coverage_report(items):
    order, by_code = collect(items)
    if not order:
        print("  TEKS: none tagged")
        return
    print(f"  TEKS coverage: {len(order)} standard(s)")
    for code in order:
        ids = ", ".join(str(i) for i in by_code[code])
        print(f"    - {code}: {len(by_code[code])} item(s) -> {ids}")
    untagged = [str(it.get("id")) for it in items if not item_teks(it)]
    if untagged:
        print(f"    (untagged: {', '.join(untagged)})")


def label_html(codes):
    """Small muted label appended to a question body, e.g. 'TEKS: 126.34(c)(4)(A)'."""
    if not codes:
        return ""
    return ("<p style='font-size:12px;color:#999;margin-top:10px;'>"
            f"<em>TEKS: {', '.join(codes)}</em></p>")
