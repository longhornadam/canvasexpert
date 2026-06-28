# PowerGrader Refactor Stage 1: Extract Static CSS And JavaScript

## Goal

Move inline PowerGrader CSS and JavaScript out of the templates into static files. Preserve UI behavior exactly.

This stage reduces template length and is intentionally frontend-only.

## Files To Change

- `api/webui/templates/powergrader_setup.html`
- `api/webui/templates/powergrader_queue.html`

## Files To Create

- `api/webui/static/powergrader_setup.css`
- `api/webui/static/powergrader_setup.js`
- `api/webui/static/powergrader_queue.css`
- `api/webui/static/powergrader_queue.js`

## Existing Static Pattern

Use the existing app pattern:

```html
<link rel="stylesheet" href="/static/example.css?v={{ asset_v }}">
<script src="/static/example.js?v={{ asset_v }}"></script>
```

Do not use `url_for`.

## Setup Template Instructions

1. In `api/webui/templates/powergrader_setup.html`, find the inline `<style>...</style>` block.
2. Move only the CSS inside that block to `api/webui/static/powergrader_setup.css`.
3. Replace the removed style block with:

   ```html
   <link rel="stylesheet" href="/static/powergrader_setup.css?v={{ asset_v }}">
   ```

4. Find the inline `<script>...</script>` block.
5. The script currently contains Jinja-rendered values:

   ```javascript
   var defaultModel = {{ default_openrouter_model | tojson }};
   var modelPresets = {{ openrouter_model_presets | tojson }};
   ```

6. Before the external script include, add this small inline config block:

   ```html
   <script>
   window.POWERGRADER_SETUP_CONFIG = {
     defaultModel: {{ default_openrouter_model | tojson }},
     modelPresets: {{ openrouter_model_presets | tojson }}
   };
   </script>
   ```

7. Move the rest of the JavaScript into `api/webui/static/powergrader_setup.js`.
8. In `powergrader_setup.js`, replace the two Jinja-backed variable declarations with:

   ```javascript
   var setupConfig = window.POWERGRADER_SETUP_CONFIG || {};
   var defaultModel = setupConfig.defaultModel || '';
   var modelPresets = setupConfig.modelPresets || [];
   ```

9. Add this script include after the config block:

   ```html
   <script src="/static/powergrader_setup.js?v={{ asset_v }}"></script>
   ```

10. Do not change element IDs, class names, endpoint URLs, or event behavior.

## Queue Template Instructions

1. In `api/webui/templates/powergrader_queue.html`, find the inline `<style>...</style>` block.
2. Move only the CSS inside that block to `api/webui/static/powergrader_queue.css`.
3. Replace the removed style block with:

   ```html
   <link rel="stylesheet" href="/static/powergrader_queue.css?v={{ asset_v }}">
   ```

4. Find the inline `<script>...</script>` block.
5. Move the JavaScript inside that block to `api/webui/static/powergrader_queue.js`.
6. Replace the removed script block with:

   ```html
   <script src="/static/powergrader_queue.js?v={{ asset_v }}"></script>
   ```

7. Do not move the `<meta name="session-id">`, `<meta name="grading-mode">`, `<meta name="mode-label">`, or `<meta name="canvas-base">` tags. The moved JavaScript must continue reading those meta tags.

## Do Not Do

- Do not rewrite the JavaScript.
- Do not convert `var` to `let` or `const`.
- Do not rename functions.
- Do not change text, labels, keyboard shortcuts, or endpoint URLs.
- Do not touch backend Python files in this stage.

## Verification

Run:

```powershell
py -m pytest api/tests/test_route_contract.py
```

Also run:

```powershell
rg -n "{{|{%" api/webui/static/powergrader_setup.js api/webui/static/powergrader_queue.js
```

The `rg` command must return no matches. Static JavaScript files must not contain Jinja template syntax.

## Acceptance Criteria

- Setup and queue templates no longer contain large inline CSS/JS blocks.
- The new static files exist.
- PowerGrader route contract is unchanged.
- Static JavaScript contains no Jinja syntax.
- Existing UI behavior is preserved.
