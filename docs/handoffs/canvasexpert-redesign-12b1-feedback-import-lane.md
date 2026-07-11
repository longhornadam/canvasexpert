# Toyota handoff 12b1: scoring-contract import lane

Implement only generic paste/file import, Feedback Scoring Contract v1 validation, and
local re-identification into PowerGrader review. Reuse `feedback_pipeline.py`, scrub,
vault, artifact/result modules, and `FeedbackExpert` storage unchanged; do not invent a
vault. Exact files/symbols come from accepted 12b0. Legacy and new UI outputs must be
contract/fixture equivalent. No AI or Canvas call. Test malformed/schema-mismatch,
unknown pseudonym/item, batch mismatch, redaction, and byte/JSON equivalence. One commit;
stop on any contract/storage change.
