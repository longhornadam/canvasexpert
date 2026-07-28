# Daily writing store format

Atomic JSON documents with an interprocess lock, following `api/operation_ledger`.
There is no `schema.sql`: nothing else in this repository uses SQLite, and a
second persistence stack with one consumer is a cost with no payer. `store/repo.py`
is the only reader and writer; `store/codec.py` is the only place records become
documents.

## Location

`<workspace>/_System/Daily Writing/`

`_System` is the workspace's PRIVATE machine-state tier, alongside the identity
vault and PowerGrader's sessions. Nothing here belongs in the repository, in
`For AI/`, or in any outbound payload.

## Layout

```
Daily Writing/
  submissions/2026-09.json      append-only, partitioned by month
  scores/2026-09.json           append-only, partitioned by month
  observations/2026-09.json     append-only, partitioned by month
  directives.json               mutable status and streaks; evaluations only grow
  reps.json                     prompts, scaffolds, passages. No student data.
  tiers.json                    canvas_id -> tier. Written only by a teacher action.
  profiles/<canvas_id>.json     derived and replaceable
  calibration/<sample_id>.json  blind-scoring sample, carries no machine scores
```

Month partitioning keeps each file small and matches how the data is read: a
four-week profile window touches one or two files. `scores_for` scans every
partition, because a score's month is the month it was *scored*, which need not
be the month the work came in.

## Identity

Every record is keyed by `canvas_id`. That key is durable: the vault lets a
teacher regenerate or hand-set a pseudonym, and a store keyed on the pseudonym
string would orphan every observation, directive, and score for that student the
moment they did.

Nothing above `store/` sees a `canvas_id`. `codec.py` swaps it for the vault
pseudonym on the way out and back on the way in, so there is exactly one place
to check when asking whether a real identifier can reach a payload. `canvas_id`
is also in `api.feedback_safety._FORBIDDEN_KEYS`, so a stored record handed
wholesale to a payload builder is hard-blocked on the key alone.

## Append-only, and why re-runs are still idempotent

`Submission`, `Score`, `Observation`, and `DirectiveEval` are only ever appended.
Readers keep the **last** entry for a given id, and ids are derived rather than
generated (`obs_id` is `<submission_id>:<pattern_tag>`).

The combination is deliberate. Re-ingesting after a segmentation fix leaves the
earlier attempt in the record for anyone auditing what the system used to think,
without letting it steer anything today. `test_dw_store_and_cli.py` asserts both
halves: the file grows, the read does not.

`RollingProfile` is the exception and is not a record. It is derived, replaceable,
and never the source of truth; deleting every profile file costs one regeneration
and no information.

## Dates

Timestamps are ISO 8601 with an offset. Two of them mean different things and are
not interchangeable:

- `scored_at` is when the checker ran. Processing time.
- `observed_at` is the submission's own timestamp. An observation is dated to the
  work it is about, because the profile window and the weekly digest select on it.
  Stamping it with the run time puts Monday's noticings in Wednesday's week and
  relocates a whole term's observations on a backfill.

## Invariants enforced at this boundary

- `score_from_dict` refuses a stored score that does not claim `history_blind`.
  A score produced by any path that saw a profile would be lying about its type.
- `profile_from_dict` goes through `models.build_profile`, so a document that
  picked up an extra key (a hand edit, an older writer, a merged OneDrive copy)
  fails with INV-5 named rather than quietly becoming a profile field nobody chose.
- `append_submission`, `append_score`, and `append_observations` each call
  `scrub.assert_clean_for_storage` before writing. Text is scrubbed at ingest and
  the unscrubbed original is never persisted; this is the second check, not the
  first.
- `put_calibration` writes no machine scores. Hiding them is a property of the
  file, not a promise about the UI.

## Running without a workspace

`Repository.default()` resolves the workspace and the identity vault.
`Repository(root, resolver=MappingResolver({...}))` needs neither, which is how
the fixtures and every test exercise the store. The CLI exposes this as
`--store-root` with `--identity-map`.
