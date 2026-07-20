# New Quizzes Response Pull Sandbox

Use this sequence to test whether CanvasExpert can pull New Quizzes responses in full, including constructed text responses, while also checking Red/Blue group-only visibility.

## Files

QuizForge files, shown in the Quiz tab library:

- `api/qf_materials/qf quiz examples/nq_pull_01_constructed_response_basics.txt`
- `api/qf_materials/qf quiz examples/nq_pull_02_red_group_text_probe.txt`
- `api/qf_materials/qf quiz examples/nq_pull_02_blue_group_text_probe.txt`
- `api/qf_materials/qf quiz examples/nq_pull_03_auto_graded_item_encoding.txt`
- `api/qf_materials/qf quiz examples/nq_pull_04_stimulus_mixed_response_probe.txt`
- `api/qf_materials/qf quiz examples/nq_pull_05_file_upload_and_essay_probe.txt`

AssignmentForge baselines, shown in the Assignment tab library after the app restarts:

- `api/qf_materials/assignment examples/af_nq_pull_baseline_text_entry.txt`
- `api/qf_materials/assignment examples/af_nq_pull_baseline_upload.txt`

The assignment examples are in a separate folder so they do not get scanned by the QuizForge fixture validator.

## Push Plan

1. Push `NQ Pull Test 01 - Constructed Response Basics` to the whole sandbox course.
2. In the Quiz tab's differentiated mode, load the course groups and map:
   - Red group -> `nq_pull_02_red_group_text_probe.txt`
   - Blue group -> `nq_pull_02_blue_group_text_probe.txt`
3. Push `NQ Pull Test 03 - Auto-Graded Item Encoding` to the whole sandbox course.
4. Push `NQ Pull Test 04 - Stimulus Mixed Response Probe` to the whole sandbox course.
5. Optionally push `NQ Pull Test 05 - File Upload And Essay Probe` if you want New Quizzes file-upload coverage.
6. Push the two AssignmentForge baseline assignments whole-class. They provide a known-good comparison lane through the normal Canvas Assignments downloader.

## Collection Notes

- Keep Student Analysis CSVs and downloaded submissions out of the repo. They contain student identifiers and response text.
- For New Quizzes, compare the manual Student Analysis CSV against any API report output you are testing.
- Use a real CSV parser for Student Analysis. Essay cells can contain HTML, commas, quotes, and literal newlines.
- Confirm whether item response cells are complete for essay, file-upload, matching, ordering, categorization, fill-in-blank, numeric, multiple-answer, and choice items.
- Confirm whether the Red and Blue group-specific quizzes are visible only to their assigned group members.
