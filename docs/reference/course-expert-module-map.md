# Course Expert Module Map

Purpose: route Course Expert debugging without re-reading the large template,
shared browser modules, and push backend.

As of 2026-07-08, Course Expert browser behavior is split into small shared
modules plus feature scripts. The large template remains mapped here because it is
mostly markup and inline Student Reports/portfolio behavior.

## Ownership

- Page template: `api/webui/templates/course_expert.html`
- Shared browser modules: `api/webui/static/push.js`, `api/webui/static/push/*.js`
- Feature browser scripts: `api/webui/static/push/*.js`
- Route owner: `api/webui/routes/push.py`
- Validation/physical routes: `api/webui/routes/push_validation.py`
- Streaming QuizForge routes: `api/webui/routes/push_streaming.py`
- In-process content push service: `api/webui/push_service.py`
- Source-material extraction: `api/webui/source_materials.py`

## Current Size Snapshot

- `api/webui/templates/course_expert.html` - 1044 lines
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
- `api/webui/static/push/assignment.js` - 126 lines
- `api/webui/routes/push.py` - 88 lines
- `api/webui/static/push/rubrics.js` - 54 lines
- `api/webui/static/push/page.js` - 51 lines
- `api/webui/static/push/rubric.js` - 41 lines
- `api/webui/static/push.js` - 8 lines

## Browser Routing

Shared modules own:

- `push/core.js` - shared escaping, form POST, log/banner, busy-state, SSE,
  printable generation, generic content push, and the `window.CE_PUSH` namespace
- `push/file_sources.js` - library/paste/upload staging and skill-copy helper
- `push/delivery.js` - datetime conversion, QuizForge delivery settings, module
  selection, module loading, and assignment group loading
- `push/rubrics.js` - RubricForge file list loading and assignment rubric controls
- `push/course_picker.js` - target-course multi-select, focused course, course
  folder lookup, and all-courses expansion
- `push.js` - tiny compatibility bootstrap that runs shared initialization

Feature scripts own:

- `push/quiz.js` - QuizForge validation, preview, whole-class push, differentiated
  push, and group manifest behavior
- `push/assignment.js` - AssignmentForge validation/push card behavior
- `push/page.js` - PageForge validation/push card behavior
- `push/rubric.js` - RubricForge validation/prompt/push card behavior
- `push/download.js` - Download Work assignment selection/download behavior

`course_expert.html` contains markup and inline JavaScript for tab switching,
delivery-option toggles, quick assignment, student reports, and combined portfolio
workflows. Standalone legacy push pages load `_push_common_scripts.html` before
their feature script.

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

- target course picker: `push/course_picker.js`
- module/category dropdowns or delivery settings: `push/delivery.js`
- QuizForge validate/preview/live stream: `push/quiz.js`, `routes/push_streaming.py`,
  `qf_pusher.py`
- Assignment/Page/Rubric card behavior: matching `push/*.js`,
  `routes/push_validation.py`, `push_service.py`
- file paste/upload issues: `push/file_sources.js`, `routes/push_validation.py`
- printable output failures: `push/core.js`, `routes/push_validation.py`,
  `engine/rendering/physical/`
- Download Work behavior: `push/download.js`, `api/downloader.py`,
  download-related routes
- Student Reports/portfolio inline behavior: `course_expert.html`,
  report/portfolio routes

## Guardrails

Do not change `LLM_Modules/*_Base.md` or Forge authoring contracts as part of UI
or routing work. Preserve DOM ids, `_push_common_scripts.html` load order, and
legacy globals (`window.CE_PUSH`, `localToISO`, `pushContent`, `targetCourses`,
`initFileSource`, `copySkill`) unless all legacy pages and feature scripts are
updated in the same change.
