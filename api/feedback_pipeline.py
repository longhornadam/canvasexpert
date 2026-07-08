"""Compatibility facade for the FeedbackExpert pipeline.

This module keeps the historical `feedback_pipeline` import path stable while the
implementation lives in smaller helper modules.
"""

try:                                   # script context (run from api/)
    from feedback_contract import CONTRACT_VERSION, _REVIEW_NOTE, _safe, build_contract_text, persona_signoff
    from feedback_artifacts import (
        _shared_context_blob,
        _scrub_bundle,
        process_inbox,
        pseudonymize,
        pseudonymize_submissions,
        reidentify_dir,
        write_bundle,
        write_safe_and_private,
    )
    from feedback_results import (
        _AI_SIGNATURE_LINE_RE,
        _DISCLOSURE_NAME_RE,
        _SECTION_LABELS,
        _format_feedback_linebreaks,
        _remove_persona_signature,
        _remove_phrase,
        normalize_ai_feedback,
        parse_results,
        reidentify,
        reidentified_csv,
        validate_results,
    )
except ModuleNotFoundError:            # package context (tests: api.feedback_pipeline)
    from api.feedback_contract import CONTRACT_VERSION, _REVIEW_NOTE, _safe, build_contract_text, persona_signoff
    from api.feedback_artifacts import (
        _shared_context_blob,
        _scrub_bundle,
        process_inbox,
        pseudonymize,
        pseudonymize_submissions,
        reidentify_dir,
        write_bundle,
        write_safe_and_private,
    )
    from api.feedback_results import (
        _AI_SIGNATURE_LINE_RE,
        _DISCLOSURE_NAME_RE,
        _SECTION_LABELS,
        _format_feedback_linebreaks,
        _remove_persona_signature,
        _remove_phrase,
        normalize_ai_feedback,
        parse_results,
        reidentify,
        reidentified_csv,
        validate_results,
    )

__all__ = [
    "CONTRACT_VERSION",
    "_REVIEW_NOTE",
    "_safe",
    "_shared_context_blob",
    "_scrub_bundle",
    "_AI_SIGNATURE_LINE_RE",
    "_DISCLOSURE_NAME_RE",
    "_SECTION_LABELS",
    "_format_feedback_linebreaks",
    "_remove_persona_signature",
    "_remove_phrase",
    "build_contract_text",
    "normalize_ai_feedback",
    "parse_results",
    "persona_signoff",
    "process_inbox",
    "pseudonymize",
    "pseudonymize_submissions",
    "reidentify",
    "reidentify_dir",
    "reidentified_csv",
    "validate_results",
    "write_bundle",
    "write_safe_and_private",
]
