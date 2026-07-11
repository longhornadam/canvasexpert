# Toyota handoff 11c1: RubricForge operation adapter

## Prerequisite and objective

Do not start until Ferrari accepts 11c0 and replaces the placeholders below in this
handoff with its exact authoritative route/service symbols. Migrate that proven path to
`content.rubric`; if 11c0 finds no live path, this slice is not Toyota-ready.

Required filled fields: **AUTHORITATIVE_ROUTE**, **SERVICE_FUNCTION**,
**CANVAS_CREATE_CALL**, **ASSOCIATION_POLICY**, **EXISTING_TESTS**.

The adapter parses the canonical contract, reviews criteria/ratings/points and targets,
records returned rubric/association IDs, and migrates both CourseExpert and standalone
Rubric surfaces. Association occurs only when explicitly reviewed. Timeout is
`sent_unknown`; same-title matching never proves success. Retry requires adapter-specific
reconciliation. Tests cover cancel, drift, duplicate, ambiguous, partial, retry,
association excluded/included, redaction, and postcondition.

Stop immediately while any placeholder remains or evidence contradicts 11c0. One commit;
run the exact tests named by 11c0 plus operation/route/JS/diff checks and report all IDs
only in untracked PRIVATE evidence.
