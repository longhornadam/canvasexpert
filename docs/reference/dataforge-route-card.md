# DataForge route card

## Teacher outcome

The teacher can import offline assessment history into CanvasExpert, inspect
standards coverage, and prepare a reviewable four-group assignment. The
Assessments surface owns import and coverage; Students owns the preview and
existing bulk group-apply path.

## One source and one identity boundary

DataForge history is local workspace state under `_System/DataForge/history/`.
The published `For AI/DataForge/standards-profile.json` is the single
pseudonym-keyed profile artifact. It contains pseudonyms, standards, and scores;
it does not contain names, Canvas IDs, or SIS IDs. Re-identification stays in
the private Identity Vault. This is pseudonymized, not anonymous, and teachers
review SAFE artifacts before sharing them with an external model.

## MCP read

`get_standards_profile()` reads the published profile offline. It has no
`course_id`, makes no Canvas request, creates no identity entry, and does not
write a file. The existing Identity Vault and outbound safety scan gate the
result. Missing, malformed, unsupported, conflicted, or unsafe state is
withheld with a structured error that does not echo a private path or value.

## Grouping and write boundary

Grouping is a local preview over current mirrored roster/group documents and
offline history. It requires exact roster coverage, always includes the explicit
No Data group, and produces Support, Core, Accelerate, and Extend with the
locked score/mastery rules. The teacher reviews the proposal before invoking the
existing digest-protected roster bulk apply transport. DataForge adds no Canvas
transport and never posts automatically.

## Off-season verification

Synthetic snapshots, rosters, groups, Identity Vault entries, and profile files
are sufficient to verify this route. No active or real course is required for
the offline profile, coverage, preview, or safety gates.
