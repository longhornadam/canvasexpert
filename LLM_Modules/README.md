# LLM Modules — Canvas Expert Authoring Documentation

Reference files for LLM-assisted authoring of Canvas content (quizzes, assignments, pages).
Load the contract(s) relevant to your task.

---

## Core

### `QuizForge_Base.md`
**Load this for every quiz generation task.**

The canonical JSON 3.0 spec. Covers all 12 question types, HTML formatting, pedagogy defaults (Bloom's, UDL, the Support/Core/Accelerate/Extend tiers), answer choice rules, rationale format, and preflight checklist.

---

### `AssignmentForge_Base.md`
**Load this for every assignment generation task.**

The canonical JSON 1.0 spec for Canvas assignments. Covers all submission types (none, on paper, online text/URL/upload/media/annotation, external tool), HTML formatting, tier scaffolding, and multi-course placeholder resolution.

---

### `PageForge_Base.md`
**Load this for every page generation task.**

The canonical JSON 1.0 spec for Canvas content pages. Covers title + rich HTML body, unit hubs, resource collections, callout styling, course-resource placeholders, and multi-course deployment.

---

### `RubricForge_Base.md`
**Load this for every rubric generation task.**

The canonical JSON 1.0 spec for Canvas rubrics. Dual-register authoring (grader voice + student voice in one file), banded range ratings, the student explainer page, and a self-contained `scoring_guidance` block so the same file drives high-quality scoring by humans and LLMs alike. Default library instances live in `api/rubrics/`.

---

### `QuizForge_example_quiz.txt`
A complete worked example covering all 12 question types with proper rationales. Use as a format reference when generating or validating quiz output.

---

### `QuizForge_Explainer.txt`
Teacher-facing overview of Canvas Expert: what it is, how it works, the three Forges, basic workflow, FAQ. Not a system prompt — load this when onboarding a new user or answering "what is this tool?"

---

## Subject Modules

### `QF_MOD_ELA_Question_Design.md`
ELA/Language Arts question design workflow. Covers distractor methodology, misconception mapping, simultaneous answer development, length-balance tracking, and a pre-generation planning template. Load in addition to QuizForge_Base when authoring ELA assessments.

---

## Reference

### `QF_REF_Stimulus_Formatting.md`
Technical reference for stimulus content rendering: prose vs. poetry auto-detection thresholds, code fence types, exact HTML output styles, the JSON → Python → HTML newline pipeline, and common LLM authoring pitfalls. Load when authoring questions with passages, code, or poetry, or when debugging rendering behavior.

---

## Usage

**Minimum for quizzes:** `QuizForge_Base.md`

**Minimum for assignments:** `AssignmentForge_Base.md`

**Minimum for pages:** `PageForge_Base.md`

**Minimum for rubrics:** `RubricForge_Base.md`

**ELA quiz:** `QuizForge_Base.md` + `QF_MOD_ELA_Question_Design.md`

**Quiz with passage/code/poetry:** `QuizForge_Base.md` + `QF_REF_Stimulus_Formatting.md`

**New user (any Forge):** `QuizForge_Explainer.txt` first, then the contract for your Forge
