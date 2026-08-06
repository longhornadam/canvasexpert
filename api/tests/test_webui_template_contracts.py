"""Source-contract tests for WebUI templates and client JS.

These guard against specific P1 regression modes. They read source files
directly — no live Canvas, no server, no student data.

Only safety/workflow-wiring tests are retained. Visual composition, CSS,
DOM IDs, layout, copy, script ordering, template inheritance, and former
redesign-slice implementation snapshots are covered by rendered-route
verification per AGENTS.md testing policy.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _slurp(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ── Typed operation-gateway routing ──────────────────────────────────

def test_operation_gateway_aliases_and_no_direct_legacy_calls():
    """All content types use typed operation aliases; no generic /api/content/push."""
    core = _slurp("api/webui/static/push/core.js")
    for alias, kind in {
        "qf": "content.quiz",
        "quick": "content.quick_assignment",
        "af": "content.assignment",
        "pf": "content.page",
        "rf": "content.rubric",
    }.items():
        assert f'{alias}: "{kind}"' in core
    for rel in (
        "api/webui/static/push/assignment.js",
        "api/webui/static/push/page.js",
        "api/webui/static/push/rubric.js",
        "api/webui/static/course_expert/quick_assignment.js",
    ):
        assert "/api/content/push" not in _slurp(rel)
    assert '{ payload: payload, targets: targets }' in core


def test_quiz_push_uses_typed_operation_payloads_only():
    """Quiz browser uses typed operation preparation, not direct SSE or student IDs."""
    quiz = _slurp("api/webui/static/push/quiz.js")
    assert 'push.pushContent(' in quiz
    assert '"qf"' in quiz
    assert '{ mode: "whole", path: path, settings: settingsObj }' in quiz
    assert '{ mode: "differentiated", variants: variants, settings: settingsObj }' in quiz
    assert "push.stream" + "SSE(" not in quiz
    assert "push.canvasWriteReview(" not in quiz
    assert "studentIds:" not in quiz


def test_operation_summary_polling_uses_ordinal_labels_only():
    """Polling endpoint must not expose internal target/step identifiers."""
    core = _slurp("api/webui/static/push/core.js")
    assert '"/api/operations/" + encodeURIComponent(operationId) + "/status"' in core
    assert "Target ' + (targetIndex + 1)" in core
    assert "Step ' + (stepIndex + 1)" in core
    assert "target.target_key" not in core
    assert "step.step_key" not in core
    assert 'window.addEventListener("pagehide"' in core


def test_shared_csrf_meta():
    """base.html must expose the shared CSRF meta tag."""
    base = _slurp("api/webui/templates/base.html")
    assert base.count('name="canvasexpert-csrf-token"') == 1
    assert 'content="{{ csrf_token }}"' in base


def test_course_expert_workspace_title_tracks_the_existing_tab_activation_path():
    """Workbench title follows the same activation path as deep links and key navigation."""
    template = _slurp("api/webui/templates/course_expert.html")
    tabs = _slurp("api/webui/static/course_expert/tabs.js")
    assert 'id="ce-workspace-title"' in template
    assert "function updateWorkspaceTitle(tabName)" in tabs
    assert "if (activated) updateWorkspaceTitle(tabName);" in tabs


def test_page_prepare_uses_shared_operation_helper():
    """Page push uses the shared prepare helper, not its own fetch/state."""
    page = _slurp("api/webui/static/push/page.js")
    assert 'push.prepareOnly("content.page"' in page
    assert "function postJson" not in page
    assert "function renderOperationsList" not in page


def test_operation_alias_runtime_cancellation_never_applies():
    """Runtime cancellation of prepare (via CE_WRITE_REVIEW.confirm=false) never applies."""
    core_path = ROOT / "api/webui/static/push/core.js"
    script = r'''
import fs from "node:fs";
import vm from "node:vm";
const calls = [];
global.window = {
  CE_WRITE_REVIEW: { confirm: async () => false },
  CE_PUSH: { targetCourses: () => [{id: "101", name: "Fictional Course"}] }
};
global.document = {
  querySelector: () => ({getAttribute: () => "csrf-test"}),
  querySelectorAll: () => [],
  getElementById: () => null,
  addEventListener: () => {}
};
global.alert = () => {};
global.fetch = async (url, options) => {
  calls.push({url, body: options && options.body});
  if (url.includes("/prepare")) return {ok: true, status: 200, json: async () => ({ok: true, operation_id: "op-test"})};
  if (url.includes("/review")) return {ok: true, status: 200, json: async () => ({ok: true, batch_id: "batch-test", review_digest: "digest", frozen_reviews: [{course_name: "Fictional Course", assignment_name: "Test"}]})};
  throw new Error("unexpected fetch " + url);
};
vm.runInThisContext(fs.readFileSync(process.argv[1], "utf8"));
const log = {hidden: true, textContent: "", scrollTop: 0, scrollHeight: 0};
for (const alias of ["quick", "af", "pf", "rf"]) {
  await window.CE_PUSH.pushContent(alias, {name: "Test"}, log, null, {disabled: false}, "Review Test");
}
if (calls.some(c => c.url === "/api/content/push" || c.url.includes("/apply"))) process.exit(2);
if (calls.filter(c => c.url.includes("/prepare")).length !== 4) process.exit(3);
if (calls.filter(c => c.url.includes("/prepare")).some(c => JSON.parse(c.body).targets[0].course_id !== "101")) process.exit(4);
'''
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, str(core_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_download_work_runtime_is_retired():
    """Course Expert must not ship the retired standalone acquisition client."""
    assert not (ROOT / "api/webui/static/push/download.js").exists()
    assert "/static/push/download.js" not in _slurp("api/webui/templates/course_expert.html")


# ── Shared Canvas-write review control ────────────────────────────────

def test_write_review_loaded_before_page_scripts():
    """write_review.js must load synchronously in <head> before any {% block content %}."""
    html = _slurp("api/webui/templates/base.html")
    wr_idx = html.index("/static/write_review.js")
    content_idx = html.index("{% block content %}")
    head_close_idx = html.index("</head>")
    assert html.count("/static/write_review.js") == 1
    assert wr_idx < content_idx, "write_review.js must load before {% block content %}"
    assert wr_idx < head_close_idx, "write_review.js must be inside <head>"
    tag_start = html.rindex("<script", 0, wr_idx)
    tag_end = html.index(">", tag_start)
    tag = html[tag_start:tag_end]
    assert "defer" not in tag
    assert "async" not in tag


def test_no_local_canvas_write_review_function():
    """No file in api/webui/static may define function canvasWriteReview."""
    import glob
    found = []
    for f in glob.glob(str(ROOT / "api/webui/static/**/*.js"), recursive=True):
        with open(f, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if "function canvasWriteReview" in line:
                    found.append(f"{f}:{i}: {line.strip()}")
    assert not found, (
        "Legacy canvasWriteReview function definitions remain:\n" +
        "\n".join(found)
    )


# ── Shared course context ─────────────────────────────────────────────

def test_course_picker_uses_shared_context_without_dual_writes():
    """CoursePicker publishes to CE_CONTEXT and does not write the legacy storage key."""
    js = _slurp("api/webui/static/push/course_picker.js")
    assert "window.CE_CONTEXT" in js
    assert "context.setFocus" in js
    assert "context.setTargets" in js
    assert "authoritative: true" in js
    assert 'fetch("/api/courses")' not in js
    assert "loadAllCoursesIntoChecklist" not in js
    assert "canvasExpert.push.coursePicker.v1" not in js


def test_current_courses_are_the_only_operational_picker_scope():
    settings = _slurp("api/webui/templates/settings.html")
    settings_js = _slurp("api/webui/static/settings/courses.js")
    dashboard = _slurp("api/webui/templates/dashboard.html")
    desk = _slurp("api/webui/static/desk.js")
    gradebook = _slurp("api/webui/static/gradebook.js")
    course_picker = _slurp("api/webui/static/push/course_picker.js")

    for heading in ("Current courses", "Previous courses", "Add courses from Canvas"):
        assert heading in settings
    assert "Move to Previous" in settings
    assert "Make Current" in settings
    assert "automatic PowerGrader work will pause" in settings_js
    assert "window.CE_CONTEXT" not in desk
    assert "context.setFocus" not in desk
    assert "context.setTargets" not in desk
    assert "reconcile(" not in desk
    assert "data-desk-start" not in dashboard
    for text in (
        "Sync now", "Checking Canvas sync…", "Syncing Canvas data…",
        "Canvas data synced ",
    ):
        assert text in dashboard or text in desk
    assert "authoritative: true" in course_picker
    assert 'fetch("/api/courses")' not in course_picker
    assert 'fetch("/api/courses")' not in gradebook


def test_desk_runtime_keeps_semantic_presentation_after_refresh():
    desk_path = ROOT / "api/webui/static/desk.js"
    script = r'''
import fs from "node:fs";
import vm from "node:vm";

class Node {
  constructor(tag, id = "") {
    this.tagName = tag;
    this.id = id;
    this.children = [];
    this.dataset = {};
    this.className = "";
    this.textContent = "";
    this.options = [];
    this.value = "";
    this.selectedIndex = 0;
  }
  appendChild(child) { this.children.push(child); return child; }
  removeChild(child) { this.children = this.children.filter(item => item !== child); }
  get firstChild() { return this.children[0] || null; }
  addEventListener() {}
  focus() {}
}

const job = {
  job_id: "job-runtime",
  material_version: "material-runtime",
  origin: "intentional",
  kind: "grade.powergrader",
  status: "attention",
  title: "PowerGrader work",
  attention_reason: "Work needs attention",
  resumable_url: "/powergrader/session/runtime",
  counts: {total: 24, pending: 22, affected: 2}
};
const presentation = {
  course_label: "Fictional Course",
  title: "Fictional Reflection",
  summary: "24 students · 22 awaiting review · 2 approved, not posted",
  action_label: "Review & post"
};
const initialData = new Node("script", "desk-initial-data");
initialData.textContent = JSON.stringify({
  jobs: [job], presentations: {"job-runtime": presentation}, operations: [], receipts: []
});
const elements = {
  "desk-root": new Node("div", "desk-root"),
  "desk-initial-data": initialData,
  "desk-continue-list": new Node("div", "desk-continue-list"),
  "desk-attention-list": new Node("div", "desk-attention-list"),
  "desk-prepared-list": new Node("div", "desk-prepared-list"),
  "desk-receipts-list": new Node("div", "desk-receipts-list")
};

global.window = {
  prompt: () => null,
  confirm: () => false
};
global.document = {
  getElementById: id => elements[id] || null,
  createElement: tag => new Node(tag),
  querySelector: selector => selector.includes("csrf") ? {content: "csrf"} : null,
  querySelectorAll: () => [],
  addEventListener: () => {}
};
global.fetch = async url => ({
  ok: true,
  json: async () => {
    if (url.startsWith("/api/work")) {
      return {ok: true, jobs: [job], presentations: {"job-runtime": presentation}};
    }
    if (url === "/api/operations") return {ok: true, operations: []};
    if (url === "/api/receipts") return {ok: true, receipts: []};
    throw new Error("unexpected fetch " + url);
  }
});

function textOf(node) {
  return [node.textContent, ...node.children.flatMap(textOf)].filter(Boolean).join(" | ");
}

vm.runInThisContext(fs.readFileSync(process.argv[1], "utf8"));
const initialText = textOf(elements["desk-attention-list"]);
await new Promise(resolve => setTimeout(resolve, 0));
const refreshedText = textOf(elements["desk-attention-list"]);
for (const rendered of [initialText, refreshedText]) {
  if (!rendered.includes("Fictional Course")) process.exit(2);
  if (!rendered.includes("Fictional Reflection")) process.exit(3);
  if (!rendered.includes("24 students · 22 awaiting review · 2 approved, not posted")) process.exit(4);
  if (!rendered.includes("Review & post")) process.exit(5);
  if (rendered.includes("grade.powergrader") || rendered.includes("24 items")) process.exit(6);
}
'''
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, str(desk_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


# ── PowerGrader ───────────────────────────────────────────────────────

def test_powergrader_visible_privacy_copy_uses_teacher_language():
    html = _slurp("api/webui/templates/powergrader_setup.html")
    autoscore = _slurp("api/webui/static/powergrader/setup_autoscore.js")
    assert "may still contain details that could identify a student" in html
    assert "identifying context" not in html
    assert "shared source material for the batch" in autoscore
    assert "shared context for the batch" not in autoscore


def test_powergrader_advanced_import_controls_are_session_bound():
    html = _slurp("api/webui/templates/powergrader_setup.html")
    queue = _slurp("api/webui/templates/powergrader_queue.html")
    assert 'id="pg-advanced-import"' in html
    assert 'id="pg-new-quiz-csv-form"' in html
    assert 'id="pg-custom-persona-form"' in html
    assert 'id="pg-feedback-pattern-form"' in html
    assert 'id="pg-import-result-file"' in queue

def test_powergrader_writing_timeline_surfaces_tracked_state_and_disclaimer():
    """The tracked flag must reach the browser, and no timeline path may conclude.

    `writing_timeline_tracked` was previously persisted on the session and read by
    nothing, so a teacher had no way to know an assignment was tracked and the queue
    could not distinguish "tracked, no trail" from "not tracked". `renderWritingTimeline`
    has since moved out of queue_core.js into the dedicated queue_writing_timeline.js
    module; the disclaimer sentence must still appear on every render path, now split
    across the two files it lives in.
    """
    queue_html = _slurp("api/webui/templates/powergrader_queue.html")
    core = _slurp("api/webui/static/powergrader/queue_core.js")
    timeline = _slurp("api/webui/static/powergrader/queue_writing_timeline.js")
    assert 'id="pg-timeline-badge"' in queue_html
    assert "pg-timeline-badge" in core
    assert "session.writing_timeline_tracked" in core
    assert "No DOCX document was examined for this submission" in core
    # renderWritingTimeline moved out of queue_core.js verbatim.
    assert "function renderWritingTimeline" not in core
    # The not-examined path stays in queue_core.js and keeps its own copy of the
    # limit statement.
    assert core.count("describes editing process, not authorship or intent") == 1
    # The unavailable and available render paths both live in the new module now.
    assert timeline.count("describes editing process, not authorship or intent") == 2


def test_powergrader_writing_timeline_module_wired_after_queue_core():
    """The new module must load after queue_core.js, and the strip mount must exist."""
    queue_html = _slurp("api/webui/templates/powergrader_queue.html")
    core_idx = queue_html.index("/static/powergrader/queue_core.js")
    timeline_idx = queue_html.index("/static/powergrader/queue_writing_timeline.js")
    assert timeline_idx > core_idx, "queue_writing_timeline.js must load after queue_core.js"
    assert 'id="pg-timeline-strip"' in queue_html


def test_powergrader_writing_timeline_module_registers_frozen_api():
    """The module must register all three frozen API names on the shared namespace."""
    js = _slurp("api/webui/static/powergrader/queue_writing_timeline.js")
    assert "window.CE_POWERGRADER_QUEUE" in js
    assert "queue.writingTimelineSignals" in js
    assert "queue.renderWritingTimelineStrip" in js
    assert "queue.renderWritingTimeline" in js


def test_powergrader_writing_timeline_strip_copy_matches_spec():
    """Strip copy must use the exact, non-accusatory phrasing specified for the feature."""
    js = _slurp("api/webui/static/powergrader/queue_writing_timeline.js")
    for phrase in (
        "Counts describe editing process, not authorship or intent.",
        "with no revision trail",
        "with another name on the file",
        "with tracking lock absent",
        "could not be read",
        "with no document",
        # "submissions examined", not "documents examined": a student who uploaded no
        # DOCX has a submission but no document, so the headline denominator counts
        # submissions. Saying "documents" would imply one exists for every student.
        "submissions examined",
    ):
        assert phrase in js, f"Missing strip copy: {phrase!r}"
    assert "documents examined" not in js


def _hex_hsl(hex_code: str):
    hex_code = hex_code.lstrip("#")
    if len(hex_code) == 3:
        hex_code = "".join(ch * 2 for ch in hex_code)
    r, g, b = (int(hex_code[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    mx, mn = max(r, g, b), min(r, g, b)
    lightness = (mx + mn) / 2
    if mx == mn:
        return 0.0, 0.0, lightness
    d = mx - mn
    sat = d / (2 - mx - mn) if lightness > 0.5 else d / (mx + mn)
    if mx == r:
        hue = ((g - b) / d) % 6
    elif mx == g:
        hue = (b - r) / d + 2
    else:
        hue = (r - g) / d + 4
    hue *= 60
    return hue, sat, lightness


def _looks_red_or_orange(hex_code: str) -> bool:
    hue, sat, lightness = _hex_hsl(hex_code)
    if sat < 0.3 or lightness < 0.15 or lightness > 0.9:
        return False
    return hue <= 45 or hue >= 345


def test_powergrader_writing_timeline_module_avoids_alarm_language_and_colors():
    """No-alarm contract: the feature reports without accusing.

    This is the most important test in the set — the entire premise of the writing
    timeline feature is that it describes editing process without implying cheating
    or misconduct, in wording and in color.
    """
    js = _slurp("api/webui/static/powergrader/queue_writing_timeline.js")
    lowered = js.lower()
    banned_terms = (
        "suspicious", "suspicion", "cheat", "plagiar", "integrity",
        "flagged", "alert", "warning", "misconduct",
    )
    hits = [term for term in banned_terms if term in lowered]
    assert not hits, f"Accusatory language found in writing timeline module: {hits}"
    assert "--ce-attention" not in js
    assert "--ce-danger" not in js
    hex_codes = re.findall(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b", js)
    alarming = [code for code in hex_codes if _looks_red_or_orange(code)]
    assert not alarming, f"Hardcoded red/orange hex colors found: {alarming}"


def test_powergrader_writing_timeline_signals_membership_and_robustness():
    """writingTimelineSignals exact index membership across clean, edge, and malformed input."""
    module_path = ROOT / "api/webui/static/powergrader/queue_writing_timeline.js"
    script = r'''
import fs from "node:fs";
import vm from "node:vm";

global.window = {};
global.document = {
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: () => ({}),
  addEventListener: () => {}
};

vm.runInThisContext(fs.readFileSync(process.argv[1], "utf8"));
const queue = window.CE_POWERGRADER_QUEUE;
if (!queue || typeof queue.writingTimelineSignals !== "function") {
  console.error("writingTimelineSignals not registered on window.CE_POWERGRADER_QUEUE");
  process.exit(2);
}

function availableReport(overrides) {
  return Object.assign({
    status: "available",
    trail_present: true,
    tracking_lock_present: true,
    properties: {
      creator_category: "submission_author",
      last_modified_by_category: "submission_author",
      total_time_minutes: 4,
      revision: 1
    },
    blocks: [],
    largest_insertions: []
  }, overrides);
}

const students = [
  // 0: clean available report
  { attachments: [{ writing_timeline: availableReport({}) }] },
  // 1: no revision trail
  { attachments: [{ writing_timeline: availableReport({ trail_present: false }) }] },
  // 2: tracking lock absent
  { attachments: [{ writing_timeline: availableReport({ tracking_lock_present: false }) }] },
  // 3: creator_category ALONE must NOT trigger otherName. Creator is the tool or
  //    template that made the file ("Microsoft Office User", a district template, a
  //    lab image), so it reads as an unrecognized author on nearly every honest
  //    document. Counting it would fire on everything and point at innocent students.
  { attachments: [{ writing_timeline: availableReport({
      properties: { creator_category: "other_roster_author", last_modified_by_category: "submission_author" }
  }) }] },
  // 4: other name ONLY inside blocks[].author_category
  { attachments: [{ writing_timeline: availableReport({
      blocks: [{ type: "insertion", timestamp: "2026-01-01T00:00:00.000Z", character_count: 20, word_count: 4, author_category: "unrecognized_author_present" }]
  }) }] },
  // 5: unreadable (status invalid)
  { attachments: [{ writing_timeline: { status: "invalid", trail_present: null, tracking_lock_present: null } }] },
  // 6: no document (empty attachments)
  { attachments: [] },
  // 7: no document (null attachments)
  { attachments: null },
  // 8: available but missing properties/blocks entirely (must not throw)
  { attachments: [{ writing_timeline: { status: "available" } }] },
  // 9: non-object attachment entries mixed with a non-timeline attachment (must not throw)
  { attachments: [null, "garbage", 42, { filename: "plain.docx" }] },
  // 10: non-object student
  null,
  // 11: non-object student
  "not-an-object",
  // 12: other name via last_modified_by_category — someone else saved the file last.
  //     Unlike creator, this DOES trigger.
  { attachments: [{ writing_timeline: availableReport({
      properties: { creator_category: "submission_author", last_modified_by_category: "other_roster_author" }
  }) }] }
];

let signals;
try {
  signals = queue.writingTimelineSignals(students);
} catch (e) {
  console.error("writingTimelineSignals threw: " + (e && e.stack || e));
  process.exit(3);
}

function eq(name, actual, expected) {
  const a = JSON.stringify((actual || []).slice().sort((x, y) => x - y));
  const e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + " expected " + e + " got " + a);
    process.exit(4);
  }
}

eq("examined", signals.examined, [0, 1, 2, 3, 4, 8, 12]);
eq("noTrail", signals.noTrail, [1]);
eq("lockAbsent", signals.lockAbsent, [2]);
// 3 is absent on purpose: creator_category alone must not count. 4 = block author,
// 12 = last_modified_by.
eq("otherName", signals.otherName, [4, 12]);
eq("unreadable", signals.unreadable, [5]);
eq("noDocument", signals.noDocument, [6, 7, 9, 10, 11]);
'''
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_powergrader_writing_timeline_render_sparkline_and_text_equivalent():
    """renderWritingTimeline sparkline + its aria text-equivalent, per the frozen spec."""
    module_path = ROOT / "api/webui/static/powergrader/queue_writing_timeline.js"
    script = r'''
import fs from "node:fs";
import vm from "node:vm";

class EscNode {
  set textContent(v) { this._text = String(v == null ? "" : v); }
  get textContent() { return this._text || ""; }
  get innerHTML() {
    return (this._text || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
}

global.window = {};
global.document = {
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: () => new EscNode(),
  addEventListener: () => {}
};

vm.runInThisContext(fs.readFileSync(process.argv[1], "utf8"));
const queue = window.CE_POWERGRADER_QUEUE;
if (!queue || typeof queue.renderWritingTimeline !== "function") {
  console.error("renderWritingTimeline not registered on window.CE_POWERGRADER_QUEUE");
  process.exit(2);
}

const report = {
  status: "available",
  trail_present: true,
  tracking_lock_present: true,
  properties: { creator_category: "submission_author", last_modified_by_category: "submission_author", total_time_minutes: 22, revision: 4 },
  blocks: [
    { type: "insertion", timestamp: "2026-01-01T00:00:00.000Z", character_count: 60, word_count: 12, author_category: "submission_author" },
    { type: "deletion", timestamp: "2026-01-01T01:00:00.000Z", character_count: 25, word_count: 4, author_category: "submission_author" },
    { type: "insertion", timestamp: "2026-01-01T02:00:00.000Z", character_count: 40, word_count: 8, author_category: "submission_author" }
  ],
  // Populated so the "Three largest insertion blocks" list — the OTHER place a
  // timestamp reaches the teacher — is covered by the Central assertions below.
  largest_insertions: [
    { type: "insertion", timestamp: "2026-01-01T00:00:00.000Z", character_count: 60, word_count: 12, author_category: "submission_author" }
  ]
};

const html = queue.renderWritingTimeline(report);

if (!html.includes("at Dec 31, 2025, 6:00 PM CST")) { console.error("largest-insertion timestamp not rendered in Central:\n" + html); process.exit(17); }

const svgMatches = html.match(/<svg\b[^>]*>/g) || [];
if (svgMatches.length !== 1) { console.error("expected exactly one <svg>, got " + svgMatches.length + ": " + JSON.stringify(svgMatches)); process.exit(3); }
const svgTag = svgMatches[0];
if (!svgTag.includes("class=\"pg-timeline-spark\"")) { console.error("missing spark class: " + svgTag); process.exit(4); }
if (!svgTag.includes("aria-hidden=\"true\"")) { console.error("missing aria-hidden: " + svgTag); process.exit(5); }
if (!svgTag.includes("height=\"40\"")) { console.error("missing height: " + svgTag); process.exit(6); }
if (!svgTag.includes("viewBox=\"0 0 300 40\"")) { console.error("missing viewBox: " + svgTag); process.exit(7); }
if (svgTag.includes("preserveAspectRatio")) { console.error("unexpected preserveAspectRatio: " + svgTag); process.exit(8); }

if (!html.includes("fill=\"var(--ce-prepared)\"")) { console.error("missing insertion fill var(--ce-prepared)"); process.exit(9); }
if (!html.includes("fill=\"var(--ce-ink-muted)\"")) { console.error("missing deletion fill var(--ce-ink-muted)"); process.exit(10); }
if (!html.includes("opacity=\"0.55\"")) { console.error("missing deletion opacity 0.55"); process.exit(11); }

const lineMatches = html.match(/<line\b[^>]*>/g) || [];
const baseline = lineMatches.find(tag => tag.includes("y1=\"36.5\"") && tag.includes("y2=\"36.5\"") && tag.includes("stroke=\"var(--ce-rule)\""));
if (!baseline) { console.error("no baseline <line> found among: " + JSON.stringify(lineMatches)); process.exit(12); }

// Central, with the CST/CDT marker spelled out. Note what this fixture proves: a
// UTC midnight is really the PREVIOUS evening in Central, so a raw UTC clock would
// show a New Year's Day session that was actually New Year's Eve at 6pm. That whole
// class of misreading is what Central exists to prevent.
const expectedSentence = "3 revision blocks from Dec 31, 2025, 6:00 PM CST to Dec 31, 2025, 8:00 PM CST. Largest single insertion is 60 characters, 60% of inserted text.";
if (!html.includes(expectedSentence)) { console.error("missing text equivalent sentence. Got html:\n" + html); process.exit(13); }
// The teacher must never be shown a UTC clock anywhere in a timeline render.
if (/\d{2}:\d{2}:\d{2}(\.\d+)?Z/.test(html)) { console.error("raw UTC timestamp leaked into rendered timeline:\n" + html); process.exit(15); }
if (html.includes("UTC")) { console.error("UTC label in rendered timeline"); process.exit(16); }

const svgEndIdx = html.indexOf(svgTag) + svgTag.length;
const sentenceIdx = html.indexOf(expectedSentence);
if (sentenceIdx < svgEndIdx) { console.error("text equivalent must immediately follow the svg"); process.exit(14); }

// All blocks have character_count 0: sparkline (and its text equivalent) must be
// omitted entirely, with no placeholder.
const zeroReport = {
  status: "available",
  trail_present: true,
  tracking_lock_present: true,
  properties: { creator_category: "submission_author", last_modified_by_category: "submission_author" },
  blocks: [
    { type: "insertion", timestamp: "2026-01-01T00:00:00.000Z", character_count: 0, word_count: 0, author_category: "submission_author" },
    { type: "deletion", timestamp: "2026-01-01T01:00:00.000Z", character_count: 0, word_count: 0, author_category: "submission_author" }
  ],
  largest_insertions: []
};
const zeroHtml = queue.renderWritingTimeline(zeroReport);
if (zeroHtml.includes("<svg")) { console.error("sparkline should be omitted when no blocks qualify. Got html:\n" + zeroHtml); process.exit(15); }
if (/revision block/.test(zeroHtml)) { console.error("text equivalent should be omitted when no blocks qualify. Got html:\n" + zeroHtml); process.exit(16); }

// Only a deletion qualifies: sparkline renders (k=1, singular phrasing), but the
// "Largest single insertion" sentence is omitted since no characters were inserted.
const deletionOnlyReport = {
  status: "available",
  trail_present: true,
  tracking_lock_present: true,
  properties: {},
  blocks: [
    { type: "deletion", timestamp: "2026-01-01T00:00:00.000Z", character_count: 15, word_count: 3, author_category: "submission_author" }
  ],
  largest_insertions: []
};
const delHtml = queue.renderWritingTimeline(deletionOnlyReport);
if (!delHtml.includes("<svg")) { console.error("sparkline should render when a deletion block qualifies. Got html:\n" + delHtml); process.exit(17); }
if (!/1 revision block\b/.test(delHtml)) { console.error("singular phrasing missing for k=1. Got html:\n" + delHtml); process.exit(18); }
if (/Largest single insertion/.test(delHtml)) { console.error("Largest single insertion sentence should be omitted when nothing was inserted. Got html:\n" + delHtml); process.exit(19); }
'''
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_powergrader_config_has_workspace():
    """POWERGRADER_SETUP_CONFIG contains hasWorkspace from has_workspace."""
    html = _slurp("api/webui/templates/powergrader_setup.html")
    assert 'hasWorkspace: {{ has_workspace | tojson }}' in html, (
        "POWERGRADER_SETUP_CONFIG missing hasWorkspace key sourced from "
        "has_workspace template variable."
    )


def test_sync_start_enabled_uses_workspace_flag():
    """syncStartEnabled gates on setupConfig.hasWorkspace."""
    js = _slurp("api/webui/static/powergrader/setup_core.js")
    assert "setupConfig.hasWorkspace" in js, (
        "syncStartEnabled does not reference setupConfig.hasWorkspace"
    )
    assert "startBtn.disabled = !(setupConfig.hasWorkspace" in js, (
        "syncStartEnabled enable condition must include hasWorkspace as "
        "the first conjunct."
    )


def test_powergrader_review_apply_contract():
    """Manual pushes review first and send the frozen token to apply."""
    js = _slurp("api/webui/static/powergrader/queue_review.js")
    assert "/push-review" in js
    assert "review_token" in js
    assert "CE_WRITE_REVIEW.confirm" in js
    assert "Apply approved grades and feedback" in js
    assert "status !== 'pushed' && result.status !== 'already_applied'" in js


def test_powergrader_ai_draft_stays_out_of_feedback_text():
    """AI draft disclosure belongs in chrome, while the textarea stays editable feedback."""
    template = _slurp("api/webui/templates/powergrader_queue.html")
    core = _slurp("api/webui/static/powergrader/queue_core.js")
    review = _slurp("api/webui/static/powergrader/queue_review.js")
    assert 'id="pg-ai-draft-badge"' in template
    assert 'data-aiDraft="false"' in template
    assert "return formatAiFeedback(st.ai_feedback);" in core
    assert "AI draft ---" not in core
    assert "feedbackEl.addEventListener('input'" in core
    assert "Restored AI feedback for editing" in review


def test_powergrader_import_uses_shared_session_id():
    """Packet links use the queue namespace session id, not an IIFE-local name."""
    js = _slurp("api/webui/static/powergrader/queue_import.js")
    assert "queue.getSessionId" in js
    assert "SESSION_ID" not in js


def test_powergrader_queue_polls_narrow_staged_route_without_auto_reload():
    js = _slurp("api/webui/static/powergrader/queue_import.js")
    template = _slurp("api/webui/templates/powergrader_queue.html")
    assert "/staged" in js
    assert "setInterval(pollStagedStatus, 30000)" in js
    assert "Your assistant staged " in js
    assert 'id="pg-load-staged"' in template
    assert "queue.reloadSession" in js


def test_powergrader_ack_before_start_button():
    """AI acknowledgment must appear after configuration and before start button."""
    html = _slurp("api/webui/templates/powergrader_setup.html")
    ack_idx = html.index('id="pg-ai-check"')
    btn_idx = html.index('id="pg-start-btn"')
    assert ack_idx < btn_idx, (
        "AI acknowledgment checkbox must appear before the start button"
    )


def _powergrader_catalog_node_prelude() -> str:
    return r'''
import fs from "node:fs";
import vm from "node:vm";

class Node {
  constructor(tag, id = "") {
    this.tagName = tag;
    this.id = id;
    this._innerHTML = "";
    this._textContent = "";
    this._value = "";
    this.options = [];
    this.hidden = false;
    this.disabled = false;
    this.dataset = {};
    this.style = {};
    this.listeners = {};
    this.classList = {
      values: new Set(),
      toggle: (name, force) => force ? this.classList.values.add(name) : this.classList.values.delete(name),
      add: name => this.classList.values.add(name),
      remove: name => this.classList.values.delete(name)
    };
  }
  set textContent(value) { this._textContent = String(value || ""); this._innerHTML = ""; }
  get textContent() { return this._textContent; }
  set innerHTML(value) {
    this._innerHTML = String(value || "");
    this._textContent = "";
    if (this.tagName === "select") {
      this.options = Array.from(this._innerHTML.matchAll(/<option value="([^"]*)"([^>]*)>/g)).map(match => ({
        value: match[1], selected: match[2].includes("selected")
      }));
      const selected = this.options.find(option => option.selected);
      this._value = selected ? selected.value : (this.options[0] ? this.options[0].value : "");
    }
  }
  get innerHTML() {
    if (this._innerHTML) return this._innerHTML;
    return this._textContent.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  }
  set value(value) {
    const wanted = String(value || "");
    if (this.tagName === "select" && this.options.length && !this.options.some(option => option.value === wanted)) {
      this._value = "";
    } else {
      this._value = wanted;
    }
  }
  get value() { return this._value; }
  addEventListener(event, callback) { this.listeners[event] = callback; }
  dispatch(event) { if (this.listeners[event]) return this.listeners[event]({target: this, preventDefault() {}}); }
}

const ids = [
  "pg-course", "pg-assignment", "pg-assignment-search", "pg-assignment-group-by",
  "pg-assignment-tools", "pg-mode", "pg-ai-options", "pg-rubric-fast", "pg-start-btn",
  "pg-start-status", "pg-ai-label", "pg-assignment-unsupported-hint", "pg-refresh-assignment",
  "pg-open-assignment-folder", "pg-evidence-status", "pg-sync-course-list", "pg-course-catalog-status"
];
const elements = Object.fromEntries(ids.map(id => [id, new Node(
  ["pg-course", "pg-assignment", "pg-assignment-group-by"].includes(id) ? "select" : "div", id
)]));
elements["pg-course"].innerHTML = '<option value=""></option><option value="course-a"></option><option value="course-b"></option><option value="course-c"></option>';
elements["pg-assignment"].innerHTML = '<option value=""></option>';
elements["pg-assignment-group-by"].innerHTML = '<option value="last_three"></option>';
elements["pg-assignment-search"].tagName = "input";
elements["pg-ai-options"].hidden = true;

global.window = {POWERGRADER_SETUP_CONFIG: {hasWorkspace: true, defaultModel: ""}};
global.document = {
  getElementById: id => elements[id] || null,
  createElement: tag => new Node(tag),
  querySelectorAll: () => [],
  querySelector: () => null
};

const tick = async (count = 8) => { for (let i = 0; i < count; i += 1) await Promise.resolve(); };
const scope = state => ({state, last_success_at: "2026-07-14T12:00:00+00:00", last_attempt_at: "2026-07-14T12:00:00+00:00", error_code: ""});
const catalog = (courseId, assignmentPrefix, moduleCount = 4) => ({
  ok: true,
  available: true,
  course_id: courseId,
  course_name: "Fictional Course",
  updated_at: "2026-07-14T12:00:00+00:00",
  source: "canonical",
  warnings: [],
  scopes: {assignments: scope("current"), modules: scope("current")},
  assignments: Array.from({length: moduleCount}, (_, index) => ({
    id: `${assignmentPrefix}-${index + 1}`,
    name: `${assignmentPrefix} Assignment ${index + 1}`,
    description_text: index === 0 ? "Special context phrase" : "Ordinary context",
    due_at: "2026-07-18T05:00:00Z",
    submission_types: ["online_text_entry"],
    quiz_id: "",
    is_quiz: false,
    quiz_kind: "",
    is_quiz_lti_assignment: false
  })),
  modules: Array.from({length: moduleCount}, (_, index) => ({
    id: `${courseId}-module-${index + 1}`,
    name: index === 0 ? "Week One Search Name" : `Module ${index + 1}`,
    position: index + 1,
    items: [],
    assignment_ids: [`${assignmentPrefix}-${index + 1}`],
    quiz_ids: []
  }))
});
'''


def test_powergrader_catalog_runtime_is_local_first_and_search_is_network_free():
    core_path = ROOT / "api/webui/static/powergrader/setup_core.js"
    script = _powergrader_catalog_node_prelude() + r'''
const calls = [];
let finishRefresh;
global.fetch = (url, options) => {
  calls.push({url, options});
  if (url === "/api/course-catalog?course_id=course-a") {
    return Promise.resolve({json: async () => catalog("course-a", "A")});
  }
  if (url === "/api/course-catalog/refresh") {
    return new Promise(resolve => { finishRefresh = payload => resolve({json: async () => payload}); });
  }
  throw new Error("unexpected fetch " + url);
};

vm.runInThisContext(fs.readFileSync(process.argv[1], "utf8"));
elements["pg-course"].value = "course-a";
window.CE_POWERGRADER_SETUP.loadCourseCatalog("course-a");
await tick();

if (!elements["pg-assignment"].innerHTML.includes("A Assignment 2")) process.exit(2);
if (elements["pg-assignment"].innerHTML.includes("A Assignment 1")) process.exit(3);
if (calls.length !== 2 || !calls[0].url.startsWith("/api/course-catalog?") || calls[1].url !== "/api/course-catalog/refresh") process.exit(4);

const beforeSearch = calls.length;
elements["pg-assignment-search"].value = "special context";
elements["pg-assignment-search"].dispatch("input");
if (!elements["pg-assignment"].innerHTML.includes("A Assignment 1")) process.exit(5);
elements["pg-assignment-search"].value = "week one search";
elements["pg-assignment-search"].dispatch("input");
if (!elements["pg-assignment"].innerHTML.includes("A Assignment 1")) process.exit(6);
elements["pg-assignment-search"].value = "";
elements["pg-assignment-search"].dispatch("input");
elements["pg-assignment-group-by"].value = "course-a-module-2";
elements["pg-assignment-group-by"].dispatch("change");
if (!elements["pg-assignment"].innerHTML.includes("A Assignment 2") || elements["pg-assignment"].innerHTML.includes("A Assignment 3")) process.exit(7);
if (calls.length !== beforeSearch) process.exit(8);

finishRefresh({ok: false, error: "synthetic failure"});
await tick();
if (!elements["pg-assignment"].innerHTML.includes("A Assignment 2") || elements["pg-assignment"].disabled) process.exit(9);
if (!elements["pg-course-catalog-status"].textContent.includes("Using the local course list")) process.exit(10);

elements["pg-sync-course-list"].dispatch("click");
await tick(2);
if (calls.length !== 3 || calls[2].url !== "/api/course-catalog/refresh") process.exit(11);
if (!String(calls[2].options.body).includes("course_id=course-a")) process.exit(12);
'''
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, str(core_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_powergrader_catalog_runtime_handles_cold_superseded_and_preserved_selection():
    core_path = ROOT / "api/webui/static/powergrader/setup_core.js"
    script = _powergrader_catalog_node_prelude() + r'''
const calls = [];
let finishAGet;
let finishBRefresh;
global.fetch = (url, options) => {
  calls.push({url, options});
  if (url === "/api/course-catalog?course_id=course-a") {
    return new Promise(resolve => { finishAGet = payload => resolve({json: async () => payload}); });
  }
  if (url === "/api/course-catalog?course_id=course-b") {
    return Promise.resolve({json: async () => catalog("course-b", "B", 1)});
  }
  if (url === "/api/course-catalog?course_id=course-c") {
    return Promise.resolve({json: async () => ({ok: true, available: false})});
  }
  if (url === "/api/course-catalog/refresh") {
    const body = String(options.body);
    if (body.includes("course_id=course-b")) {
      return new Promise(resolve => { finishBRefresh = payload => resolve({json: async () => payload}); });
    }
    if (body.includes("course_id=course-c")) {
      return Promise.resolve({json: async () => catalog("course-c", "C", 1)});
    }
  }
  throw new Error("unexpected fetch " + url);
};

vm.runInThisContext(fs.readFileSync(process.argv[1], "utf8"));
elements["pg-course"].value = "course-a";
window.CE_POWERGRADER_SETUP.loadCourseCatalog("course-a");
elements["pg-course"].value = "course-b";
window.CE_POWERGRADER_SETUP.loadCourseCatalog("course-b");
await tick();
finishAGet(catalog("course-a", "A", 1));
await tick();
if (!elements["pg-assignment"].innerHTML.includes("B Assignment 1") || elements["pg-assignment"].innerHTML.includes("A Assignment 1")) process.exit(2);

elements["pg-assignment"].value = "B-1";
finishBRefresh(catalog("course-b", "B", 1));
await tick();
if (elements["pg-assignment"].value !== "B-1") process.exit(3);

const postsBeforeRepeat = calls.filter(call => call.url === "/api/course-catalog/refresh").length;
window.CE_POWERGRADER_SETUP.loadCourseCatalog("course-b");
await tick();
const postsAfterRepeat = calls.filter(call => call.url === "/api/course-catalog/refresh").length;
if (postsAfterRepeat !== postsBeforeRepeat) process.exit(4);

elements["pg-course"].value = "course-c";
window.CE_POWERGRADER_SETUP.loadCourseCatalog("course-c");
await tick(12);
if (!elements["pg-assignment"].innerHTML.includes("C Assignment 1")) process.exit(5);
if (!elements["pg-course-catalog-status"].textContent.includes("Course list synced")) process.exit(6);
'''
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, str(core_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
