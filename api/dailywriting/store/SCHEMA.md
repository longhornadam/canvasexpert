# Writing Record store format

`store/repo.py` is the only reader and writer, and `store/codec.py` is the
only document codec. The workspace-private location is
`<workspace>/_System/WritingReps/`.

```
WritingReps/
  submissions/YYYY-MM.json
  reps.json
```

`reps.json` is the one source of truth for retained assignment context:
stable rep ID, reliable date, prompt, supplied scaffolds/source text when
available, word cap, and section. `submissions/YYYY-MM.json` is append-only
scrubbed evidence, keyed on disk by Canvas ID. Readers use the last entry for
a stable submission ID, so re-ingest is current-record idempotent while an
earlier attempt remains auditable in the private file.

The identity resolver changes Canvas ID to pseudonym only at the repository
boundary. Real identifiers never reach the projection. Ingest scrubs before
segmentation, and `append_submission` checks the stored text again before
writing. Timestamps are offset-aware ISO 8601; window reads select by the
student's submitted date. Writes use an interprocess lock and atomic replace.

Writing Record stores evidence only: it has no score, rubric outcome, tier,
directive, profile, feedback, calibration, or derived assessment record.
