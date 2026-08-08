# Oral-reading evidence contract

Ordinary local media review is the default: a validated `downloaded` or `reused`
record is playable by its own session-scoped stream even when another manifest record
is held. Read-aloud analysis is a separate, explicit, default-off teacher selection.
When it is off, no passage or local speech model is required and the session records
`{"enabled": false}`. A local-only
`faster-whisper` `small.en` CPU/int8 adapter may produce a teacher review report;
it never sends audio, transcript, word events, paths, identifiers, or model-cache
state to an AI/SAFE/packet/write lane.

When read-aloud is selected, the teacher supplies a separate confirmed passage of 1–3,000 normalized English
words. Version 1.0 normalization is NFKC, casefold, curly-apostrophe conversion,
and peripheral-punctuation trimming, preserving internal apostrophes/hyphens.
Reports bind canonical-audio SHA-256, attempt, passage SHA-256, model identity and
version, normalization and alignment versions. A changed binding is not reusable.

Alignment uses deterministic edit-distance priority: exact, substitution, omission,
then insertion. Accuracy and WCPM count exact words only; candidates for repetitions
and self-corrections do not change either metric. WCPM uses the full recording
duration. Low word confidence (<0.70), unsupported language, empty audio, or over
100 candidate differences is `needs_review`; otherwise the report is `complete`.
Failures and a missing model are `unavailable`.

One selected run constructs the local transcriber once and shares it across its
recordings; a construction failure produces an `unavailable` report per recording.
Only the teacher queue receives the passage, transcript, aggregate metrics,
uncertainty, and at most 100 timestamped candidates. Word events remain private in
the session. The browser plays canonical local audio through its existing
session-scoped stream, never a private path or Canvas URL. Model weights are
downloaded only after the explicit local setup action; normal grading never starts a
download. The default cache is `%LOCALAPPDATA%\CanvasExpert\speech-models`, or the
machine-local `CANVAS_EXPERT_WHISPER_MODEL_CACHE` override.
