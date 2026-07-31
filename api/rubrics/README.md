# Default Rubric Library

Bundled `<RUBRICFORGE_JSON>` rubrics the Canvas Expert offers when attaching a rubric
to an assignment. Contract: [`Author a Rubric (RubricForge).txt`](../default_docs/AI%20Authoring/Author%20a%20Rubric%20%28RubricForge%29.txt) (v1.0-json).

One file = one Canvas rubric. Each file also defines its student-facing explainer
page (`student_page`), which the pusher renders and links from assignments via
`{{page:<title>}}`. The `scoring_guidance` block makes each file self-contained for
scoring sessions, human or LLM.

| File | Title (resolution key) | Flavor | Scale |
|---|---|---|---|
| `ELA7_Classroom_Writing_Rubric.txt` | ELA 7 Standard Writing Rubric | classroom | 0–100, five analytic categories (SCR + ECR, proportional) |
| `ELA_STAAR_ECR_Rubric.txt` | STAAR ECR Rubric (0-5) | staar | D&O 0–3 + Conventions 0–2 |
| `ELA_STAAR_SCR_Rubric.txt` | STAAR SCR Rubric (0-2) | staar | single holistic criterion |
| `ELA_District_ECR_Rubric.txt` | District ECR Rubric (0-10) | district | STAAR doubled — D&O 0–6 + Conventions 0–4, range bands |

Push defaults: rubric is created course-level once (found by title thereafter),
associated to every assignment (including each tier of a tiered push), and
**assignment points are set to match the rubric total** when attached for grading
(teacher can override to feedback-only in the Expert).

Teachers add their own rubrics by dropping RubricForge JSON files here (authored
in conversation per the contract).
