# Toyota handoff 14b2: secondary read/manage surface adoption

## Objective

Apply the final shell/context vocabulary to Course Info, Student Reports, Download Work,
AI Expert, and About without inventing jobs or ledgers for read-only pages.

## Files

- `api/webui/templates/{course,student_reports,download_work,ai_expert,about}.html`
- `api/webui/static/course_info.js`
- `api/webui/static/course_expert/student_reports.js`
- `api/webui/static/course_expert/portfolio.js` only where the report page already uses it
- `api/webui/static/workbench.css`
- Relevant template/route/report/source tests and docs

## Behavior

- Course Info and Student Reports consume shared focused course.
- Download Work remains focused-course-only and never implies multi-course write scope.
- AI Expert/About use the new typography/shell but no fake Work rail or operation ledger.
- Welcome remains a focused onboarding wizard and is not changed.

Preserve every route, deep link, ID, script order, report/download behavior, and open-path
safety. Render at 1920/2560 in both themes, verify context/deep links, no unintended page
scroll, zero console errors. Stop if a page needs behavior change to fit the shell.

```powershell
py -m pytest api/tests/test_portfolio_merged.py api/tests/test_nq_report.py api/tests/test_downloader.py api/tests/test_source_materials.py api/tests/test_workspace.py api/tests/test_webui_template_contracts.py api/tests/test_route_contract.py
git diff --check
```

Run `node --check` for every changed browser file. One commit; report hash/files,
commands/pass counts, every affected route/theme/width, context/deep-link/open-path checks,
console count, and no Canvas write/download of private work during verification.
