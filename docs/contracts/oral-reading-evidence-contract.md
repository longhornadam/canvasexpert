# Oral-reading evidence contract

Ordinary Canvas media recordings are private PowerGrader evidence.  A local-only
`faster-whisper` `small.en` CPU/int8 adapter may produce a teacher review report;
it never sends audio, transcript, word events, paths, identifiers, or model-cache
state to an AI/SAFE/packet/write lane.

The teacher supplies a separate confirmed passage of 1–3,000 normalized English
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

Only the teacher queue receives the passage, transcript, aggregate metrics,
uncertainty, and at most 100 timestamped candidates. Word events remain private in
the session. The browser plays canonical local audio through its existing
session-scoped stream, never a private path or Canvas URL. Model weights are
downloaded only after the explicit local setup action; normal grading never starts a
download. The default cache is `%LOCALAPPDATA%\CanvasExpert\speech-models`, or the
machine-local `CANVAS_EXPERT_WHISPER_MODEL_CACHE` override.
