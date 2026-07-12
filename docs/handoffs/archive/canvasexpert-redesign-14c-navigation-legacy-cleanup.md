# Toyota handoff 14c: final navigation and proven-dead cleanup

Make top-level navigation Desk, Create, Grade, Students, Automations, plus compact system/
readiness access. Never add “Teacher Jobs.” After accepted 12b5, remove FeedbackExpert
from top-level navigation but keep `/feedback-expert` rendering its full legacy page with
the compatibility notice for this release—no redirect, hash/query translation, backend
removal, or workspace rename.

After each content adapter has migrated both UI surfaces, standalone `/push/*` GET entry
routes return 302 to exact `/course-expert?tab=<kind>` destinations while preserving
supported query parameters. No server-side fragment promise. Keep POST compatibility APIs
until a later release. Preserve `/assessment`, `/name-manager`, course/gradebook and PG
session deep links, theme/context fallback keys, and open-path safety.

Edit `base.html`, `_workbench_header.html`, `routes/pages.py`, standalone route owners,
`feedback_expert.html`, scoped CSS, route/template tests, AGENTS/READMEs/module maps.
Remove a file/symbol/rule only after exact `rg` call-site proof and rendered parity; do
not guess at unnamed migration partials.

Run full API tests, route/template contracts, every changed JS through `node --check`,
and diff check. Render every route, redirect query, Feedback page, and deep link in both
themes/widths; confirm globals, overflow, and zero console errors. Stop on incomplete
parity or any caller. One commit; report hash, deliberate route delta, redirect matrix,
removed-symbol searches, and every-route evidence.
