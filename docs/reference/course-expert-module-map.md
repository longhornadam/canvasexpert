# Work Tools Module Map

Purpose: route Work tools debugging without re-reading the page template,
shared push modules, and the feature scripts that own the remaining browser
workflows.

As of 2026-07-08, Work tools browser behavior is split into small shared
push modules plus page-specific feature scripts. `course_expert.html` is now
mostly markup, data injection, and script includes.

## Ownership

- Page template: `api/webui/templates/course_expert.html`
- Shared browser modules: `api/webui/static/push.js`, `api/webui/static/push/*.js`
- Work tools feature scripts: `api/webui/static/course_expert/*.js`
- Route owner: `api/webui/routes/push.py`
- Validation/physical routes: `api/webui/routes/push_validation.py`
- Streaming QuizForge routes: `api/webui/routes/push_streaming.py`
- In-process content push service: `api/webui/push_service.py`
- Source-material extraction: `api/webui/source_materials.py`

## Current Size Snapshot

- `api/webui/templates/course_expert.html` - 699 lines
- `api/webui/static/course_expert/tabs.js` - 114 lines
- `api/webui/static/course_expert/student_reports.js` - 111 lines
- `api/webui/static/course_expert/portfolio.js` - 110 lines
- `api/webui/static/course_expert/quick_assignment.js` - 34 lines
- `api/webui/static/course_expert/work_rail.js` - new Work rail sidebar (replaces legacy sidebar navigation)
- `api/webui/push_service.py` - 472 lines
- `api/webui/source_materials.py` - 420 lines
- `api/webui/static/push/quiz.js` - 294 lines
- `api/webui/static/push/download.js` - 246 lines
- `api/webui/static/push/core.js` - 207 lines
- `api/webui/static/push/course_picker.js` - 180 lines
- `api/webui/static/push/delivery.js` - 161 lines
- `api/webui/static/push/file_sources.js` - 160 lines
- `api/webui/routes/push_validation.py` - 160 lines
- `api/webui/routes/push_streaming.py` - 147 lines
- `api/webui/static/push/assignment.js` - 136 lines
- `api/webui/routes/push.py` - 88 lines
- `api/webui/static/push/page.js` - 57 lines
- `api/webui/static/push/rubrics.js` - 54 lines
- `api/webui/static/push/rubric.js` - 47 lines
- `api/webui/static/push.js` - 8 lines

## Browser Routing

Shared modules own:

- `push/core.js` - shared escaping, form POST, log/banner, busy-state, SSE,
  printable generation, generic content push, and the `window.CE_PUSH` namespace
- `push/file_sources.js` - library/paste/upload staging and skill-copy helper;
  still provides the legacy `initFileSource` and `copySkill` globals
- `push/delivery.js` - datetime conversion, QuizForge delivery settings, module
  selection, module loading, and assignment group loading; still provides
  `localToISO`
- `push/rubrics.js` - RubricForge file list loading and assignment rubric controls
- `push/course_picker.js` - target-course multi-select, focused course, course
  folder lookup, and all-courses expansion; still provides `targetCourses`
- `push.js` - tiny compatibility bootstrap that runs shared initialization

Work tools feature scripts own:

- `course_expert/tabs.js` - tab activation, query/hash deep-linking, delivery
  option toggles, whole/differentiated quiz mode switching, file-source bootstrap,
  copy-skill wiring, and course-picker dismiss behavior; the shared seam is
  `window.CE_COURSE_EXPERT`
- `course_expert/student_reports.js` - roster load, monitor toggle, and student
  packet SSE
- `course_expert/portfolio.js` - New Quizzes CSV portfolio and merged portfolio
  forms
- `course_expert/quick_assignment.js` - quick gradebook-column push

Shared push scripts still own the core push cards:

- `push/quiz.js` - QuizForge validation, preview, whole-class push, differentiated
  push, and group manifest behavior
- `push/assignment.js` - AssignmentForge validation/push card behavior
- `push/page.js` - PageForge validation/push card behavior
- `push/rubric.js` - RubricForge validation/prompt/push card behavior
- `push/download.js` - Download Work assignment selection/download behavior

`course_expert.html` now contains markup plus script includes. Standalone legacy
push pages load `_push_common_scripts.html` before their feature script; Course
Expert loads that bundle first, then the shared push cards, then the page-specific
`course_expert/*.js` files.

## Backend Routing

`routes/push.py` owns the router, Canvas module/assignment group lookup, and generic
`/api/content/push` fan-out.

`routes/push_validation.py` owns:

- `/api/temp-upload`
- `/api/validate`, `/api/af/validate`, `/api/pf/validate`, `/api/rf/validate`
- `/api/physical/quiz`
- RubricForge scoring prompt route

`routes/push_streaming.py` owns:

- `/api/push/preview`
- `/api/push/stream`
- `/api/push-multi-whole/stream`
- `/api/push-variants/stream`
- `/api/push-multi/stream`

`push_service.py` owns in-process assignment/page/quick/printable pushes and the
AssignmentForge/PageForge/RubricForge service path. QuizForge live pushes still run
through CLI subprocess/streaming routes.

## First Places To Look By Symptom

- Work tools tab deep-linking / shell glue: `course_expert/tabs.js`
- Work tools Student Reports: `course_expert/student_reports.js`
- Work tools NQ / merged portfolio forms: `course_expert/portfolio.js`
- Work tools quick assignment: `course_expert/quick_assignment.js`
- target course picker: `push/course_picker.js`
- module/category dropdowns or delivery settings: `push/delivery.js`,
  `course_expert/tabs.js`
- QuizForge validate/preview/live stream: `push/quiz.js`, `routes/push_streaming.py`,
  `qf_pusher.py`
- Assignment/Page/Rubric card behavior: matching `push/*.js`,
  `routes/push_validation.py`, `push_service.py`
- file paste/upload issues: `push/file_sources.js`, `routes/push_validation.py`
- printable output failures: `push/core.js`, `routes/push_validation.py`,
  `engine/rendering/physical/`
- Download Work behavior: `push/download.js`, `api/downloader.py`,
  download-related routes
- Student Reports/portfolio inline behavior: `course_expert/student_reports.js`,
  `course_expert/portfolio.js`, report/portfolio routes

## Guardrails

Do not change `LLM_Modules/*_Base.md` or Forge authoring contracts as part of UI
or routing work. Preserve DOM ids, `_push_common_scripts.html` load order, and
legacy globals (`window.CE_PUSH`, `localToISO`, `pushContent`, `targetCourses`,
`initFileSource`, `copySkill`) unless all legacy pages and feature scripts are
updated in the same change.
