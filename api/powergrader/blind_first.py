"""PowerGrader blind-first scoring — commit your own score before seeing the AI's.

The queue's default is to pre-fill the score box from ``ai_score``, which anchors
the teacher on the model's number before they have formed a judgment of their own.
Blind-first withholds ``ai_score`` and ``ai_feedback`` until the teacher records a
score for that student, then reports whether the two agree.

Withholding happens **server-side** in :func:`project_session`, not by hiding a
populated field in the browser. A number that reached the page has already had its
chance to anchor, and "hidden" is one accidental unhide away from visible. The
browser is never sent an AI score for a student it has not revealed.

The blind capture is also the reason this feature earns its keep beyond bias: every
reveal records what the teacher scored *before* seeing the model, so the session
accumulates an honest per-assignment agreement record instead of a pile of grades
that silently inherited the model's number.

Blind capture is teacher-only session data. It never enters a Canvas payload, a
push receipt, or a SAFE artifact — see ``docs/reference/powergrader-scoring-map.md``.
"""

from datetime import datetime, timezone
from functools import wraps

from api.powergrader import session_store


# Score myself has no AI suggestion to withhold, so blind-first is meaningless there.
ELIGIBLE_MODES = ("assisted", "packet")

# Points of disagreement the teacher considers not worth a second look.
DEFAULT_THRESHOLD = 1.0
MAX_THRESHOLD = 1000.0


def _session_locked(func):
    """Keep injected-loader actions inside the authoritative session lock."""
    @wraps(func)
    def wrapped(session_id, *args, **kwargs):
        with session_store.session_lock(session_id):
            return func(session_id, *args, **kwargs)
    return wrapped


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _coerce_score(raw) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _truthy(raw) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def is_eligible(session: dict) -> bool:
    """Blind-first only means something when an AI suggestion exists to withhold."""
    return bool(session) and session.get("mode") in ELIGIBLE_MODES


def settings(session: dict) -> dict:
    """Normalized blind-first settings, safe to read on any session shape."""
    raw = session.get("blind_first") if isinstance(session, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    threshold = _coerce_score(raw.get("threshold"))
    if threshold is None or threshold < 0:
        threshold = DEFAULT_THRESHOLD
    return {
        "eligible": is_eligible(session),
        "enabled": bool(raw.get("enabled")) and is_eligible(session),
        "threshold": min(threshold, MAX_THRESHOLD),
        "enabled_at": raw.get("enabled_at") or "",
    }


def is_active(session: dict) -> bool:
    return settings(session)["enabled"]


def has_ai_suggestion(student: dict) -> bool:
    if not isinstance(student, dict):
        return False
    if student.get("ai_score") is not None:
        return True
    return bool((student.get("ai_feedback") or "").strip())


def is_revealed(student: dict) -> bool:
    return bool(isinstance(student, dict) and student.get("ai_revealed"))


def is_withheld(session: dict, student: dict) -> bool:
    """True when this student's AI suggestion must not reach the browser yet."""
    return is_active(session) and not is_revealed(student)


def verdict(delta: float | None, threshold: float) -> str:
    """How much attention this disagreement deserves.

    ``uncommitted`` — revealed without a blind score, so there is nothing to compare.
    ``agrees``      — within threshold; the teacher's score stands unexamined.
    ``disagrees``   — past threshold; worth a second look before approving.
    """
    if delta is None:
        return "uncommitted"
    return "agrees" if delta <= threshold else "disagrees"


def project_session(session: dict) -> dict:
    """A response copy with every unrevealed AI suggestion withheld.

    Returns the session unchanged when blind-first is off, so an existing session
    behaves exactly as it did before this feature existed. Never mutates the stored
    session: a redacted student is copied before its AI fields are dropped, because
    the caller holds the same dict the session file will be written from.
    """
    if not isinstance(session, dict) or not is_active(session):
        return session

    students = session.get("students")
    if not isinstance(students, list):
        return session

    projected = []
    withheld_count = 0
    for student in students:
        if not isinstance(student, dict) or not is_withheld(session, student):
            projected.append(student)
            continue
        redacted = dict(student)
        # Existence is disclosed, the value is not: the queue has to tell
        # "hidden until you score" apart from "the model never scored this one",
        # and a bare boolean cannot anchor a number.
        redacted["blind_withheld"] = True
        redacted["blind_has_ai_suggestion"] = has_ai_suggestion(student)
        redacted["ai_score"] = None
        redacted["ai_feedback"] = ""
        projected.append(redacted)
        withheld_count += 1

    if not withheld_count:
        return session

    view = dict(session)
    view["students"] = projected
    view["blind_first_withheld"] = withheld_count
    return view


def summary(session: dict) -> dict:
    """Session-level blind-first state for the queue strip."""
    state = settings(session)
    students = session.get("students") if isinstance(session, dict) else None
    students = students if isinstance(students, list) else []
    scored = [s for s in students if isinstance(s, dict) and has_ai_suggestion(s)]
    revealed = [s for s in scored if is_revealed(s)]
    committed = [s for s in revealed if s.get("blind_score") is not None
                 and s.get("ai_score") is not None]
    disagreements = [s for s in committed
                     if verdict(_coerce_score(s.get("blind_delta")), state["threshold"]) == "disagrees"]
    return {
        **state,
        "ai_scored": len(scored),
        "revealed": len(revealed),
        "withheld": len(scored) - len(revealed) if state["enabled"] else 0,
        "compared": len(committed),
        "disagreements": len(disagreements),
    }


@_session_locked
def set_enabled(session_id: str, *, enabled: str, threshold: str,
                load_session, save_session) -> tuple[dict, int]:
    """Turn blind-first on or off for one session, and set its threshold."""
    session = load_session(session_id)
    if not session:
        return {"ok": False, "code": "session_not_found", "error": "Session not found."}, 404
    if not is_eligible(session):
        return {"ok": False, "code": "blind_first_ineligible",
                "error": "Blind-first needs an AI-scored session; Score myself has no suggestion to withhold."}, 200

    want = _truthy(enabled)
    current = settings(session)
    threshold_val = _coerce_score(threshold)
    if threshold_val is None:
        threshold_val = current["threshold"]
    if threshold_val < 0:
        return {"ok": False, "code": "invalid_threshold",
                "error": "The agreement threshold cannot be negative."}, 200

    state = {
        "enabled": want,
        "threshold": min(threshold_val, MAX_THRESHOLD),
        "enabled_at": current["enabled_at"] or (_iso(_now()) if want else ""),
    }
    if want and not current["enabled"]:
        state["enabled_at"] = _iso(_now())
    session["blind_first"] = state
    # Turning blind-first off never un-reveals a student: a score the teacher has
    # already seen cannot be un-seen, and rewriting the record to claim otherwise
    # would make the agreement log a lie.
    save_session(session)
    return {"ok": True, "blind_first": summary(session)}, 200


def _capture_blind(student: dict, captured: float | None, feedback: str) -> None:
    """Write the one-shot blind record for a student.

    Callers must check ``has_blind_capture`` first. Overwriting an existing capture
    is the single failure this feature cannot tolerate: the second value was formed
    after the teacher saw the model, so recording it would turn the agreement log
    into a record of the model agreeing with itself.
    """
    student["blind_score"] = captured
    student["blind_feedback"] = str(feedback or "").strip()
    student["blind_recorded_at"] = _iso(_now())
    # An empty score box is recorded as an uncommitted reveal rather than refused.
    # Blocking it would trap a teacher on an empty submission, and a truthful
    # "they looked first" beats a clean-looking but wrong record.
    student["blind_committed"] = captured is not None
    ai_score = _coerce_score(student.get("ai_score"))
    student["blind_delta"] = (abs(captured - ai_score)
                              if captured is not None and ai_score is not None else None)


def has_blind_capture(student: dict) -> bool:
    return bool(isinstance(student, dict) and student.get("blind_recorded_at"))


def record_implicit_blind(session: dict, student: dict, teacher_score: float | None,
                          teacher_feedback: str, status: str) -> bool:
    """Capture a blind score for a teacher who approved without ever revealing.

    Unlocked on purpose: the caller already holds the session lock, and the
    interprocess half of :func:`session_store.session_lock` is not reentrant.

    This is the cleanest calibration datapoint the feature produces — the teacher
    scored and moved on without consulting the model at all. It deliberately does
    **not** set ``ai_revealed``: they never saw the suggestion, so it stays withheld
    if they come back to this student.
    """
    if not is_active(session) or status == "skipped":
        return False
    if is_revealed(student) or has_blind_capture(student):
        return False
    if teacher_score is None:
        return False
    _capture_blind(student, teacher_score, teacher_feedback)
    student["blind_source"] = "approved_without_reveal"
    return True


@_session_locked
def reveal(session_id: str, *, user_id: str, blind_score: str, blind_feedback: str,
           load_session, save_session) -> tuple[dict, int]:
    """Record the teacher's independent score, then hand back the AI's.

    Idempotent by design. A second reveal returns the same AI suggestion and leaves
    the original blind capture intact — re-recording it after the teacher has seen
    the model's number would overwrite the one value this feature exists to protect.
    """
    session = load_session(session_id)
    if not session:
        return {"ok": False, "code": "session_not_found", "error": "Session not found."}, 404
    if not is_eligible(session):
        return {"ok": False, "code": "blind_first_ineligible",
                "error": "This session has no AI suggestion to reveal."}, 200

    student = next((item for item in session.get("students", [])
                    if str(item.get("user_id")) == str(user_id)), None)
    if not student:
        return {"ok": False, "code": "student_not_found", "error": "Student not found in session."}, 200

    state = settings(session)
    already = is_revealed(student)
    changed = False
    if not has_blind_capture(student):
        _capture_blind(student, _coerce_score(blind_score), blind_feedback)
        student["blind_source"] = "reveal"
        changed = True
    if not already:
        student["ai_revealed"] = True
        changed = True
    if changed:
        save_session(session)

    delta = _coerce_score(student.get("blind_delta"))
    return {
        "ok": True,
        "already_revealed": already,
        "user_id": str(user_id),
        "ai_score": student.get("ai_score"),
        "ai_feedback": student.get("ai_feedback") or "",
        "blind_score": student.get("blind_score"),
        "blind_committed": bool(student.get("blind_committed")),
        "delta": delta,
        "threshold": state["threshold"],
        "verdict": verdict(delta, state["threshold"]),
        "blind_first": summary(session),
    }, 200
