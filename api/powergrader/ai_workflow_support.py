"""Support helpers for PowerGrader AI workflow result shaping."""

from __future__ import annotations


AI_MANUAL_REVIEW_MESSAGE = "No AI draft was produced; manual grading is required."


def workflow_result(
    *,
    ok: bool,
    error: str = "",
    status_code: int = 200,
    privacy_steps: list[dict] | None = None,
    privacy_artifacts: dict | None = None,
    ai_by_uid: dict | None = None,
    ai_item_by_uid: dict | None = None,
    ai_failures: dict | None = None,
    packet_zip: str | None = None,
    budget=None,
    debug_path: str | None = None,
    copilot_packet: dict | None = None,
    source_context: dict | None = None,
) -> dict:
    return {
        "ok": ok,
        "error": error,
        "status_code": status_code,
        "privacy_steps": privacy_steps or [],
        "privacy_artifacts": privacy_artifacts or {},
        "ai_by_uid": ai_by_uid or {},
        "ai_item_by_uid": ai_item_by_uid or {},
        "ai_failures": ai_failures or {},
        "packet_zip": packet_zip,
        "budget": budget,
        "debug_path": debug_path,
        "copilot_packet": copilot_packet,
        "source_context": source_context or {},
    }


def build_privacy_artifacts(write_result: dict, safe_dir: str, private_dir: str) -> dict:
    return {
        "safe_folder": safe_dir,
        "private_folder": private_dir,
        "safe_bundle": write_result.get("safe_bundle"),
        "private_bundle": write_result.get("private_bundle"),
        "who_is_who": write_result.get("who_is_who"),
        "how_to_score": write_result.get("how_to_score"),
        "shared_context": write_result.get("shared_context"),
        "shared_context_excluded": write_result.get("shared_context_excluded"),
        "student_txt_count": len(write_result.get("student_txts") or []),
        "attachment_only_count": len(write_result.get("attachment_only") or []),
        "excluded_count": len(write_result.get("excluded") or []),
        "media_hold_count": len(write_result.get("media_holds") or []),
    }


def append_source_context_step(privacy_steps: list[dict], privacy_step, source_context: dict, warning_text: str) -> None:
    if not source_context.get("materials"):
        return
    privacy_steps.append(privacy_step(
        "source_context", "Loaded shared source material", "warn" if warning_text else "ok",
        (
            f"{len(source_context['materials'])} source item(s), "
            f"~{source_context.get('tokens_est', 0):,} input token(s)."
            + (f" {warning_text}" if warning_text else "")
        ),
    ))
