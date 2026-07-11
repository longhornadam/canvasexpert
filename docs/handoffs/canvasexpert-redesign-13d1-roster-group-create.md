# Toyota handoff 13d1: Canvas group-set and group creation

Migrate only live Canvas group-set/group creation to typed `roster.group_set` and
`roster.group` adapters. Local nicknames, pseudonyms, notes, monitoring, protected names,
and extra-time settings remain immediate PRIVATE edits. Server reloads current group
state, freezes explicit course/name/count review, records returned IDs, and handles each
group as a target. Timeout is ambiguous Attention; name matching is not success proof.
Test cancel, drift, partial groups, returned IDs, repeat, reconciliation, redaction, and
local-edit non-entry. One commit using roster group routes/helpers and focused tests.
