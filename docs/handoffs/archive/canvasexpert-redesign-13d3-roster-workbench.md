# Toyota handoff 13d3: Roster Workbench lenses

Render the existing single roster dataset through `workbench_base.html` with
Accommodations, Groups, Monitoring, Privacy, and Issues lenses. Use the shared extension
blocks and do not reload Workbench CSS. Do not duplicate forms,
DOM IDs, state, or move Name Manager's privacy ownership. Existing deep links/globals and
immediate local edit behavior remain. Live group actions use 13d1/2. Edit roster template,
scoped modules/CSS and template/roster tests; render both themes at 1920/2560 with zero
page overflow/console errors. One commit; stop if a lens creates a second state owner.
