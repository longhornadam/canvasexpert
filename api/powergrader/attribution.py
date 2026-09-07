"""Attribution for feedback an assistant wrote rather than the teacher.

Feedback posted through PowerGrader arrives in Canvas under the teacher's own
name, because it is their token and their gradebook. That is correct for words
they wrote and wrong for words an assistant drafted: a student reading it has
no way to tell the difference, and neither does the teacher six weeks later.

Every outbound path that can carry assistant-authored prose runs it through
``attribute`` first, so the wording lives in exactly one place and cannot drift
between the reviewed assignment push, automatic posting, and New Quiz item
finalization.
"""

AUTOFEEDBACK_PREFIX = "Autofeedback from an automated assistant:"


def attribute(text: str) -> str:
    """Mark assistant-authored feedback. Idempotent, and leaves empty text alone.

    Empty stays empty so a caller can keep using falsiness to decide whether to
    send a comment at all. Re-prefixing is a no-op so a value that round-trips
    through a session file cannot accumulate banners.
    """
    body = str(text or "").strip()
    if not body or body.startswith(AUTOFEEDBACK_PREFIX):
        return body
    return f"{AUTOFEEDBACK_PREFIX}\n\n{body}"


def _normalize(text: str) -> str:
    return " ".join(str(text or "").split()).casefold()


def is_assistant_authored(outbound: str, ai_feedback: str) -> bool:
    """True when outbound feedback is the assistant's draft, not the teacher's.

    PowerGrader has one feedback box. "Use AI's feedback" copies the draft into
    it, after which the stored text alone cannot say who wrote it, so this
    compares the two. A teacher who accepted the draft and appended a line still
    counts as assistant-authored, because the assistant's words are the bulk of
    what the student receives. A teacher who replaced it entirely does not, and
    their writing goes out unmarked as it should.
    """
    draft = _normalize(ai_feedback)
    if not draft:
        return False
    return _normalize(outbound).startswith(draft)
