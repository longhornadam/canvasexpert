"""The single authorization boundary for actual OpenRouter scoring sends."""
from __future__ import annotations

import time

from api import feedback_safety, openrouter_client, operational_log


class TransmissionSafetyBlocked(ValueError):
    """Raised when a full or exact outbound bundle fails the local privacy gate."""


class TransmissionBudgetBlocked(ValueError):
    """Raised when provider pricing/model authorization fails closed."""

    def __init__(self, budget: dict):
        self.budget = budget if isinstance(budget, dict) else {}
        super().__init__("OpenRouter scoring was blocked because the model price could not be verified.")


def _duration_ms(started: float) -> int:
    return max(0, int(round((time.monotonic() - started) * 1000)))


def _emit(outcome: str, started: float, *, error_class=None, count: int | None = None) -> None:
    operational_log.emit(
        "ai.transmission",
        outcome,
        duration_ms=_duration_ms(started),
        error_class=error_class,
        count=count,
    )


def _students(bundle: dict) -> list[dict]:
    return [student for student in (bundle or {}).get("students") or []
            if isinstance(student, dict)]


def _exact_bundle(bundle: dict, students: list[dict]) -> dict:
    return {**(bundle or {}), "students": students}


def _scan_or_block(bundle: dict, vault) -> None:
    verdict = feedback_safety.scan_payload(bundle, vault)
    if not verdict.get("green"):
        raise TransmissionSafetyBlocked("The Safe AI Packet did not pass the local privacy check.")


def score_openrouter_bundle(
    bundle: dict,
    vault,
    rubric_text: str,
    persona: dict,
    *,
    api_key: str,
    model: str,
    feedback_pattern: dict | None,
    output_tokens_per_student: int,
    budget_http_get=None,
    transport=None,
) -> dict:
    """Scan, budget-check, and send one pseudonymized scoring bundle."""
    started = time.monotonic()
    students = _students(bundle)
    requested = len(students)
    try:
        _scan_or_block(bundle, vault)
    except TransmissionSafetyBlocked as exc:
        _emit("blocked", started, count=requested)
        raise exc
    except Exception as exc:
        _emit("failed", started, error_class=type(exc), count=requested)
        raise

    try:
        budget = openrouter_client.teacher_workflow_budget(
            bundle,
            rubric_text,
            model,
            student_count=requested,
            persona=persona,
            feedback_pattern=feedback_pattern,
            output_tokens_per_student=output_tokens_per_student,
            http_get=budget_http_get,
        )
    except Exception as exc:
        _emit("failed", started, error_class=type(exc), count=requested)
        raise
    if not budget.get("ok"):
        _emit("blocked", started, count=requested)
        raise TransmissionBudgetBlocked(budget)

    transport = transport or openrouter_client.score
    media_students = [
        student for student in students
        if any(response.get("media") for response in student.get("responses") or [])
    ]
    media_pseudonyms = {str(student.get("pseudonym") or "") for student in media_students}
    text_students = [
        student for student in students
        if str(student.get("pseudonym") or "") not in media_pseudonyms
    ]
    results: list = []
    failures: list[tuple[str, Exception]] = []

    def send_one(sub_students: list[dict]) -> None:
        sub_bundle = _exact_bundle(bundle, sub_students)
        try:
            _scan_or_block(sub_bundle, vault)
        except TransmissionSafetyBlocked as exc:
            for student in sub_students:
                failures.append((str(student.get("pseudonym") or ""), exc))
            return
        except Exception:
            exc = TransmissionSafetyBlocked("The Safe AI Packet could not be verified before sending.")
            for student in sub_students:
                failures.append((str(student.get("pseudonym") or ""), exc))
            return
        try:
            results.extend(transport(
                sub_bundle,
                rubric_text,
                persona,
                api_key=api_key,
                model=model,
                feedback_pattern=feedback_pattern,
                model_metadata=budget.get("model_metadata"),
            ))
        except Exception as exc:
            for student in sub_students:
                failures.append((str(student.get("pseudonym") or ""), exc))

    if text_students:
        send_one(text_students)
    for student in media_students:
        send_one([student])

    successful = len({
        str(row.get("pseudonym") or "")
        for row in results
        if isinstance(row, dict) and row.get("pseudonym")
    })
    if not results and failures:
        last_error = failures[-1][1]
        _emit(
            "blocked" if isinstance(last_error, TransmissionSafetyBlocked) else "failed",
            started,
            error_class=type(last_error),
            count=requested,
        )
        raise last_error

    _emit("ok", started, count=successful)
    return {
        "results": results,
        "failures": failures,
        "budget": budget,
        "requested": requested,
        "successful": successful,
    }
