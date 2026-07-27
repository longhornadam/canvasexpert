"""Source-contract tests for WebUI templates and client JS.

These guard against specific P1 regression modes. They read source files
directly — no live Canvas, no server, no student data.

Only safety/workflow-wiring tests are retained. Visual composition, CSS,
DOM IDs, layout, copy, script ordering, template inheritance, and former
redesign-slice implementation snapshots are covered by rendered-route
verification per AGENTS.md testing policy.
"""

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
    return
    core_path = ROOT / "api/webui/static/push/core.js"
    download_path = ROOT / "api/webui/static/push/download.js"
    script = r'''
import fs from "node:fs";
import vm from "node:vm";

const calls = [];
const alerts = [];
let loadAssignments;
const rows = [];
const button = {
  disabled: false,
  textContent: "Load assignments…",
  addEventListener: (event, callback) => {
    if (event === "click") loadAssignments = callback;
  }
};
const tbody = {
  innerHTML: "",
  appendChild: (row) => rows.push(row)
};
const elements = {
  "btn-load-assignments": button,
  "dl-tbody": tbody,
  "dl-assignment-table": {hidden: true, addEventListener: () => {}},
  "dl-filter-wrap": {hidden: true},
  "dl-date-bar": {hidden: true},
  "dl-visible-count": {textContent: ""}
};

global.window = {
  CE_WRITE_REVIEW: {confirm: async () => false},
  CE_PUSH: {
    targetCourses: () => [{id: "101", name: "Fictional Course"}],
    currentCourseId: () => "course 101",
    currentCourseName: () => "Fictional Course",
    loadCourseFolder: () => {}
  },
  addEventListener: () => {}
};
global.document = {
  querySelector: () => null,
  querySelectorAll: () => [],
  getElementById: (id) => elements[id] || null,
  createElement: () => ({dataset: {}, classList: {add: () => {}}, innerHTML: ""}),
  addEventListener: () => {}
};
global.alert = (message) => alerts.push(message);
global.fetch = async (url) => {
  calls.push(url);
  if (url === "/api/assignments-full?course_id=course%20101") {
    return {
      json: async () => ({
        ok: true,
        assignments: [{
          id: "assignment-1",
          name: "Fictional Assignment",
          submission_types: ["online_text_entry"],
          due_at: "",
          points_possible: 42,
          points: 7
        }]
      })
    };
  }
  throw new Error("unexpected fetch " + url);
};

vm.runInThisContext(fs.readFileSync(process.argv[1], "utf8"));
if (typeof window.CE_PUSH.esc !== "function" || typeof window.CE_PUSH.postForm !== "function") process.exit(2);
if (window.esc !== undefined || window.postForm !== undefined) process.exit(3);
vm.runInThisContext(fs.readFileSync(process.argv[2], "utf8"));
if (typeof loadAssignments !== "function") process.exit(4);
await loadAssignments.call(button);
if (alerts.length) process.exit(5);
if (calls.length !== 1 || calls[0] !== "/api/assignments-full?course_id=course%20101") process.exit(6);
if (rows.length !== 1 || !rows[0].innerHTML.includes("<td>42</td>")) process.exit(7);
if (rows[0].innerHTML.includes("<td>7</td>")) process.exit(8);
if (button.disabled || button.textContent !== "Load assignments…") process.exit(9);
'''
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, str(core_path), str(download_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


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
    could not distinguish "tracked, no trail" from "not tracked".
    """
    queue_html = _slurp("api/webui/templates/powergrader_queue.html")
    core = _slurp("api/webui/static/powergrader/queue_core.js")
    assert 'id="pg-timeline-badge"' in queue_html
    assert "pg-timeline-badge" in core
    assert "session.writing_timeline_tracked" in core
    # Every render path — available, unavailable, and not-examined — carries the
    # same limit statement.
    assert core.count("describes editing process, not authorship or intent") == 3
    assert "No DOCX document was examined for this submission" in core


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


def test_powergrader_import_uses_shared_session_id():
    """Packet links use the queue namespace session id, not an IIFE-local name."""
    js = _slurp("api/webui/static/powergrader/queue_import.js")
    assert "queue.getSessionId" in js
    assert "SESSION_ID" not in js


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
