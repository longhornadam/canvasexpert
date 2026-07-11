# Toyota handoff 00: redesign baseline and ownership gate

## Objective

Establish a reviewed baseline before any Desk/Workbench/Instrument implementation.
This is a read-only/reconciliation gate, not a product commit.

## Required checks

1. Read `AGENTS.md`, the redesign index, both new contracts, and every active handoff.
2. Run `git fetch --all --prune`, then report current branch and ahead/behind counts for
   `origin/dev` and `origin/main` without merging.
3. Inventory `git status --short`; identify ownership of every change overlapping:
   `base.html`, `style.css`, PowerGrader setup template/CSS/JS, template-contract tests,
   route-contract tests, and module maps.
4. Ferrari/user must accept, revise, or archive `webui-09` and both PowerGrader setup
   handoffs. Toyota does not decide acceptance or archive them.
5. Preserve unrelated engine changes and the existing handoff archive move.

## Baseline commands

```powershell
py -m pytest api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py api/tests/test_workspace.py api/tests/test_powergrader_module_picker.py api/tests/test_powergrader_packet.py api/tests/test_powergrader_import_results.py -q
git diff --check
```

Expected baseline at specification time: 54 focused tests passed. A different count is
not automatically failure; report the exact collected/pass count and diff causing change.

## Acceptance evidence

- Fetch/branch comparison and dirty-file ownership report.
- Exact active handoffs and their accepted/deferred state.
- Exact test commands/results.
- Explicit list of files safe for slice 01 ownership.
- Confirmation that no file was edited, staged, committed, merged, or archived by Toyota.

## Stop conditions

Stop if overlapping ownership is unresolved, baseline tests fail, fetching changes the
understood branch relationship, or cleanup would require deleting/moving user changes.

