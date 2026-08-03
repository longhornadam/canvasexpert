# DataForge merge — Slice 5: Identity Vault migration

Status: Accepted GREEN; retired after Slice 5 verification.

## Objective

Retire the DataForge-specific re-identification map from the live DataForge workflow.
Use CanvasExpert's existing Identity Vault as the only persistent pseudonym source,
re-key existing history snapshots where the old local ID resolves to a current Vault
entry, and preserve unmatched historical scores as anonymous aggregate rows without
leaving the old pseudonym in the repository workspace.

Slice 4 is accepted GREEN under the user's off-season synthetic-testing waiver. This
slice likewise uses synthetic Vault entries, legacy CSV maps, and history snapshots in
tests only; no active course, real token, or live Canvas call is required.

## Required context

- `AGENTS.md`
- `docs/handoffs/senior level/dataforge-merge-initiative.md`, sections 4.1, 4.4,
  6, 7, 8.3, 9, 10, and 11
- `api/feedback_vault.py`
- `api/webui/workspace.py`, `identity_vault_dir`
- `api/dataforge/paths.py`
- `api/dataforge/history_store.py`
- `api/dataforge/profile_export.py`
- `api/dataforge/eduphoria_parser.py`
- `api/dataforge/views.py`
- `api/webui/routes/assessments.py`
- `api/webui/routes/roster_assessment_groups.py`
- nearest DataForge and Identity Vault tests under `api/tests/`

## Locked decisions

- The Identity Vault remains keyed by Canvas `user_id`; the SIS/Local ID is only a
  join attribute. Never add a SIS-keyed second vault namespace.
- A legacy pseudonym migrates only when its legacy Local ID matches exactly one Vault
  entry's `sis_id`. Ambiguous, missing, or stale entries do not get guessed.
- Migrated students use the Vault's existing pseudonym. Unmatched historical student
  rows retain their score/band values as anonymous aggregate rows with no legacy
  pseudonym or ID, and are ignored by pseudonym-keyed profile/grouping consumers.
- The migration is fail-closed: malformed legacy CSV, duplicate linked keys, or a
  failed snapshot rewrite leaves the legacy map in place and reports the error.
- After every snapshot and profile has been safely migrated/rebuilt, the legacy map
  and its `.bak` are removed from the private DataForge zone. No legacy map is copied
  into the Identity Vault.
- New anonymized assessment processing resolves identity through the existing Vault;
  no new persistent map or Canvas transport is introduced. A student without a
  current Vault entry is emitted only as an anonymous aggregate.
- Existing non-DataForge consumers of `feedback_vault.Vault` retain their current
  behavior. Compatibility symbols for old unit fixtures may remain isolated in a
  legacy-only module, but live DataForge views/routes may not instantiate them.

## In scope

- Pure legacy-map parsing, old-pseudonym-to-Vault re-key planning, and atomic snapshot
  migration under `api/dataforge/`.
- A Vault-backed identity provider for DataForge parser artifacts, leak checks, history,
  profile publishing, and coverage joins.
- Assessments processing/coverage wiring to the Vault-backed provider.
- Synthetic migration/provider laws and focused route/dataforge gates.

## Explicit non-goals

- No new Canvas calls, roster sync, SIS import, operation-ledger lane, or group-write
  change.
- No change to Vault's public JSON schema, pseudonym pool, or teacher Name Manager UI.
- No migration of unrelated PowerGrader/DailyWriting artifacts in this slice.
- No real student names, SIS IDs, real map files, active courses, or live Canvas calls
  in the test suite.

## Acceptance criteria

1. DataForge's live processing and coverage paths use the Identity Vault and no longer
   instantiate the DataForge `NameAnonymizer` or write `anonymize_map.csv`.
2. Synthetic migration maps exactly resolvable legacy students to Vault pseudonyms,
   blanks unmatched student identity while preserving score data, rejects ambiguous
   links, is idempotent, and removes the legacy map only after successful completion.
3. Snapshot/profile output contains no legacy pseudonym or legacy local ID after a
   successful migration; anonymous aggregate rows are not treated as named students.
4. A failed/malformed migration is fail-closed and leaves the legacy map and source
   snapshots recoverable.
5. Focused DataForge/Identity Vault/Assessments gates pass, and the full API suite is
   GREEN or any unrelated baseline failure is recorded exactly.

## Stop conditions

Stop and report RED/YELLOW if Vault entries cannot be matched without guessing, if
history/profile consumers require legacy pseudonyms, if migration needs a schema
change outside the named surfaces, or if any test needs a real course or Canvas.

## Verification gate

Use synthetic-only focused tests first. At integration checkpoint run
`py -m pytest api/tests -p no:randomly`; no live-course verification is owed.

## Execution result

Traffic light: GREEN. Synthetic/off-season verification was used under the user's explicit
waiver; no active real course or live Canvas call was required.

- Full API gate: `py -m pytest api/tests -p no:randomly` — 2077 passed.
- Focused Slice 5 gate: `py -m pytest api/tests/dataforge/test_identity_vault_migration.py api/tests/dataforge/test_grouping.py api/tests/webui/routes/test_assessments.py api/tests/webui/routes/test_roster_assessment_groups.py api/tests/test_presentation_contracts.py api/tests/test_route_contract.py -p no:randomly` — 34 passed.
- Broader DataForge/route matrix: 247 passed.
- Rendered `/assessments` with no configured courses: native page and Identity Vault status rendered; horizontal overflow false; browser console warnings/errors zero.
- Changed implementation surfaces: `api/dataforge/identity.py`, Vault-backed DataForge views/coverage, migration tests, and identity-facing copy; existing Canvas transport and Vault schema unchanged.
- No real map, student data, active course, live Canvas call, new dependency, or new transport was introduced.
- No unresolved Slice 5 decisions.
