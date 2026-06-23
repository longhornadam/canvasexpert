# Handoff — Noun-based top nav (dropdowns)

**Lane:** Toyota (well-scoped UI change, no guardrail surface).
**Status:** ready to implement.

## Goal

Replace the flat top-nav links with **category (noun) dropdowns** that expose the
discrete task pages we split out of the old "Experts." The teacher's mental model is
the *object* they're working on (Roster, Assignments, Gradebook, Feedback), and the
tasks inside each are ordered by lifecycle (create → collect → assess).

Final nav (left to right), after the brand logo:

```
Roster      Assignments ▾      Gradebook ▾      Feedback ▾
```

Right-side cluster (Settings · About · theme toggle) is **unchanged**.

- **Roster** — a single console, so a plain link (not a dropdown).
- **Assignments ▾**, **Gradebook ▾**, **Feedback ▾** — `<details class="nav-dd">` dropdowns.

There is already a complete dropdown system in the codebase — `.nav-dd`, `.nav-dd summary`,
`.dd-menu`, `.dd-menu a`, `.dd-disabled` in `style.css` (lines ~95–124), and the open/close
JS (close on outside click, collapse siblings when one opens) in `base.html`. **Reuse it.**
Do not write new dropdown JS or CSS except the one tiny separator rule noted below.

## Files to change

1. `api/webui/templates/base.html` — the `<nav>` block.
2. `api/webui/routes/pages.py` — `nav_section` values so the right dropdown highlights.
3. `api/webui/static/style.css` — add one `.dd-sep` rule (only if you use separators).
4. `api/webui/templates/dashboard.html` — re-label the "More tools by job" lanes from
   verbs to the same four nouns (Part 2 below; do it in the same PR for taxonomy
   consistency).

---

## Part 1 — `base.html` nav

**Replace** the current `<nav>…</nav>` block:

```html
<nav>
  <a class="nav-link nav-roster{% if nav_section == 'roster' %} nav-active{% endif %}" href="/roster">Roster</a>
  <a class="nav-link nav-gradebook{% if nav_section == 'gradebook' %} nav-active{% endif %}" href="/gradebook">Gradebook</a>
  <a class="nav-link nav-feedback{% if nav_section == 'feedback' %} nav-active{% endif %}" href="/feedback-expert">Feedback</a>
  <a class="nav-link nav-ai{% if nav_section == 'ai' %} nav-active{% endif %}" href="/ai-expert">AI Tools</a>
</nav>
```

**with** this block:

```html
<nav>
  <a class="nav-link nav-roster{% if nav_section == 'roster' %} nav-active{% endif %}" href="/roster">Roster</a>

  <details class="nav-dd{% if nav_section == 'assignments' %} nav-dd--active{% endif %}">
    <summary>Assignments ▾</summary>
    <div class="dd-menu">
      <a href="/push/quiz">Push quiz</a>
      <a href="/push/assignment">Push assignment</a>
      <a href="/push/page">Push page</a>
      <a href="/push/rubric">Push rubric</a>
      <a href="/push/quick">Quick assignment</a>
      <div class="dd-sep"></div>
      <a href="/download-work">Download student work</a>
    </div>
  </details>

  <details class="nav-dd{% if nav_section == 'gradebook' %} nav-dd--active{% endif %}">
    <summary>Gradebook ▾</summary>
    <div class="dd-menu">
      <a href="/gradebook?tab=policy">Policy &amp; sweep</a>
      <a href="/gradebook?tab=extra-time">Extra-time</a>
      <a href="/gradebook?tab=extensions">Extensions</a>
      <a href="/gradebook?tab=curves">Curves</a>
      <a href="/gradebook?tab=snapshot">Snapshot</a>
      <a href="/gradebook?tab=routines">Routines</a>
    </div>
  </details>

  <details class="nav-dd{% if nav_section in ['feedback', 'ai'] %} nav-dd--active{% endif %}">
    <summary>Feedback ▾</summary>
    <div class="dd-menu">
      <a href="/feedback-expert">Score with AI</a>
      <a href="/feedback-expert#push-section">Push feedback to Canvas</a>
      <a href="/student-reports">Student reports</a>
      <div class="dd-sep"></div>
      <a href="/ai-expert">AI tools &amp; skills</a>
    </div>
  </details>
</nav>
```

Notes / edge cases:
- The `summary` already shows a caret via the `▾` glyph; the default `<details>` marker is
  hidden by existing CSS (`.nav-dd summary::-webkit-details-marker { display:none }`). Do not
  add another marker.
- `nav-dd--active` is an **existing** class (`style.css:107`) — it just whitens the summary.
- The gradebook tab links use `?tab=<name>` — verified supported by `gradebook.js`
  (reads `?tab=` or `#hash` on load, line ~188). Tab names are exactly:
  `policy`, `extra-time`, `extensions`, `curves`, `snapshot`, `routines`.
- `#push-section` is a real anchor in `feedback_expert.html` (line 114).

---

## Part 1b — `pages.py` `nav_section`

The dropdowns highlight off `nav_section`. Set them so the active dropdown lights up:

- In `_push_base_ctx(request)` change `"nav_section": ""` → `"nav_section": "assignments"`.
  (This covers push quiz/assignment/page/rubric/quick **and** download-work — all
  "Assignments".)
- In `student_reports_page`, override it back to feedback:
  ```python
  @router.get("/student-reports", response_class=HTMLResponse)
  def student_reports_page(request: Request):
      return templates.TemplateResponse(
          "student_reports.html",
          {**_push_base_ctx(request), "nav_section": "feedback"},
      )
  ```
- Leave existing routes as-is: `/roster`→`roster`, `/gradebook`→`gradebook`,
  `/routines`→`gradebook`, `/feedback-expert`→`feedback`, `/ai-expert`→`ai`.

---

## Part 1c — `style.css` separator (only if using `.dd-sep`)

Add near the other `.dd-menu` rules (~line 121):

```css
.dd-sep { height: 1px; margin: 6px 0; background: var(--line); }
```

If you'd rather skip separators, delete the two `<div class="dd-sep"></div>` lines instead
and don't touch CSS.

---

## Part 2 — dashboard taxonomy alignment (same PR)

The dashboard's "More tools by job" section currently uses **verb** lane headers
(`Create / Manage / Assess / Review / Delegate`). With the nav now organized by **nouns**,
those two taxonomies disagree. Re-label and regroup that one section's lanes to match the
nav's four nouns. In `dashboard.html`, replace the five `.dash-lane` blocks inside
`<section class="dash-tools">` with four:

```html
<div class="dash-lane">
  <h3>Roster</h3>
  <a href="/roster">Roster names</a>
  <a href="/roster?focus=extra-time">Extra-time roster</a>
  <a href="/roster?focus=groups">Course roster &amp; groups</a>
</div>

<div class="dash-lane">
  <h3>Assignments</h3>
  <a href="/push/quiz">Push quiz</a>
  <a href="/push/assignment">Push assignment</a>
  <a href="/push/page">Push page</a>
  <a href="/push/rubric">Push rubric</a>
  <a href="/push/quick">Quick assignment</a>
  <a href="/download-work">Download student work</a>
  <a href="/forge/quizforge/" target="_blank" rel="noopener">Open QuizForge compiler</a>
</div>

<div class="dash-lane">
  <h3>Gradebook</h3>
  <a href="/gradebook?tab=policy">Late policy &amp; sweep</a>
  <a href="/gradebook?tab=extensions">Extensions</a>
  <a href="/gradebook?tab=curves">Curves</a>
  <a href="/gradebook?tab=snapshot">Gradebook snapshot</a>
  <a href="/gradebook?tab=routines">Routines</a>
</div>

<div class="dash-lane">
  <h3>Feedback</h3>
  <a href="/feedback-expert">Score with AI</a>
  <a href="/feedback-expert#push-section">Push feedback to Canvas</a>
  <a href="/student-reports">Student reports</a>
  <a href="/ai-expert">AI tools &amp; skills</a>
</div>
```

Leave the **"Most common jobs"** card and the **Recent activity** section untouched —
they're shortcuts/feed, not a taxonomy, so they don't clash. Leave the `/course`
(Course info) link wherever it currently is, or drop it under Assignments — implementer's
call, low stakes.

---

## Acceptance criteria

1. Top nav shows: **Roster** (link), **Assignments ▾**, **Gradebook ▾**, **Feedback ▾**,
   then the unchanged right cluster.
2. Each dropdown opens on click, closes on outside-click, and closes when another opens
   (existing JS — verify, don't rewrite).
3. Every dropdown link navigates to the right page; gradebook links land on the correct
   tab; `Push feedback to Canvas` scrolls to the push section.
4. The dropdown whose section you're in shows the active (whitened) summary:
   on any `/push/*` or `/download-work` page → **Assignments** active; on `/gradebook`
   or `/routines` → **Gradebook** active; on `/feedback-expert`, `/ai-expert`, or
   `/student-reports` → **Feedback** active; on `/roster` → **Roster** active.
5. Dashboard "More tools by job" lanes are the four nouns, matching the nav.
6. Dark mode looks correct (existing `.dd-menu` dark rules already cover it).

## Tests / how to run

```powershell
py -m pytest api/tests          # full suite must stay green
cd api; py qf_ui.py             # http://127.0.0.1:8765 — click every dropdown item
```

No new HTTP routes are added, so `api/tests/test_route_contract.py` should pass unchanged.
If it fails, you changed a route by accident — revert that.

## Do NOT touch

- `LLM_Modules/*_Base.md` authoring contracts.
- Push/validation logic or the JS modules' behavior: `push.js`, `roster.js`,
  `gradebook.js`, `course_info.js` (you may rely on them; don't edit them).
- The task page bodies themselves (`push_quiz.html`, `push_assignment.html`,
  `push_page.html`, `push_rubric.html`, `push_quick.html`, `download_work.html`,
  `student_reports.html`, `_course_picker.html`) — they're done.
- The `/course-expert` and `/assessment` redirects in `pages.py` — leave them.
  (`course_expert.html` is now orphaned but harmless; deleting it is a separate cleanup,
  not part of this task.)
- Guardrails: no Canvas token, student PII, or district-specific URLs/labels in any
  file you touch. This change is markup + nav_section strings only — keep it that way.
```
