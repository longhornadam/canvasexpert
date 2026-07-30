# WebUI presentation system

The presentation system separates private route behavior from shared visual chrome.
`base.html` is the private document root. Only templates in `layouts/` extend it.
Every live page extends a layout and receives only the
`ui/tokens.css`, `ui/foundation.css`, `ui/components.css`, and `ui/layouts.css`
bundle, in that order. Feature CSS belongs in `static/pages/` or its existing
page-owned stylesheet and is added through `head_extra`.

## Template API

- `layouts/workspace.html`: `workspace_variant`, `workspace_header`, `left_rail`,
  `primary`, `right_rail`, and `workspace_scripts`.
- `layouts/document.html`: `document_variant`, `primary`, and `document_scripts`.
- `layouts/wizard.html`: `primary` and `wizard_scripts`. It deliberately has no app
  header or readiness script so first-run setup stays focused.
- `layouts/_app_header.html`: the single migrated app header. It preserves the
  readiness strip and `theme-toggle` ID.
- `ui/_macros.html`: `page_header`, `panel`, `notice`, `empty_state`,
  `action_bar`, and `rail`. Native form controls remain native HTML.

Workspace variants are `full`, `three`, and `left-main`. The layout owns outer
columns and responsive reflow; a page owns only real rail contents. At 1180px the
right rail flows below the stage; at 760px all workspace variants become one column.

## CSS ownership

- `tokens.css`: palette, type, radius, shadow, spacing, and widths.
- `foundation.css`: reset and native element defaults.
- `components.css`: shared component vocabulary (`ce-shell`, `ce-panel`, `ce-rail`,
  `ce-page-header`, `ce-btn`, `ce-field`, `ce-tabs`, `ce-notice`, `ce-actions`,
  `ce-table`, `ce-status-dot`, `ce-empty`).
- `layouts.css`: header, outer shells, and responsive columns.
- Feature CSS: page layout only; it consumes tokens and does not introduce palette,
  font, radius, or shadow literals.

Shared component classes are never JavaScript selectors. Behavior selectors use an
ID, existing feature class, or `data-ce-hook`.

## Migration map

The enforcement registry is `api/tests/test_presentation_contracts.py`. It is the
source of truth for route, template, layout, variant, rail count, and migration state.
Home and both PowerGrader routes use `workspace/full`; Create uses
`workspace/three`; Gradebook, Roster, and Settings use `workspace/left-main`;
Routines, Student Reports, Course Info, and About use `document/wide`; AI Expert
uses `document/standard`; and Welcome uses `wizard`. The document layout required
no interface adjustment at first use. The wizard shell provides the same responsive
outer-gutter ownership as the other layouts while intentionally omitting the app
header.

All registry rows are migrated. Its source checks are repo-wide: every live template
is layout-backed and free of static inline styles, all feature CSS consumes shared
tokens, and no live template can reference the removed legacy stylesheet pair.
`style.css`, `workbench.css`, `workbench_base.html`, `_workbench_header.html`,
`name_manager.html`, and `_course_picker.html` are retired; the route redirects they
previously accompanied remain route behavior, not template dependencies.

## Change propagation

| Change | Owner |
|---|---|
| Palette, type, radius, shadow | `ui/tokens.css` (and component consumption) |
| Header/navigation chrome | `layouts/_app_header.html` |
| Outer columns/responsive reflow | `ui/layouts.css` |
| Shared panel structure | `ui/_macros.html` or `ui/components.css` |
| Feature-only layout | page stylesheet |

Partials move with their first consumer. `_readiness_strip.html` moved with the
migrated header; `_push_common_scripts.html` remains behavior-only and keeps its
script order.
