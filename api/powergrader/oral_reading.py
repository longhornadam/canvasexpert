"""Local-only read-aloud evidence for ordinary Canvas media recordings.

This module has no Canvas or AI-client dependency.  The model is deliberately
loaded only after its files have been installed by the explicit setup action.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

from api.platform_services import config


MODEL_ID = "small.en"
COMPUTE_TYPE = "int8"
NORMALIZATION_VERSION = "1.0"
ALIGNMENT_VERSION = "1.0"
CONFIDENCE_FLOOR = 0.70
MAX_PASSAGE_TOKENS = 3000
MAX_DIFFERENCES = 100
REPORT_STATUSES = ("complete", "needs_review", "unavailable")
_WORD = re.compile(r"^[a-z]+(?:['-][a-z]+)*$")


def model_cache_dir() -> Path:
    """Return the machine-local cache, never a workspace/session location."""
    return Path(config.get_whisper_model_cache())


def _model_snapshot() -> Path | None:
    root = model_cache_dir() / "models--Systran--faster-whisper-small.en" / "snapshots"
    if not root.is_dir():
        return None
    snapshots = sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name)
    return snapshots[-1] if snapshots else None


def model_status() -> dict:
    snapshot = _model_snapshot()
    return {"available": bool(snapshot), "model_id": MODEL_ID,
            "approximate_download_mib": 500}


class LocalTranscriberUnavailable(RuntimeError):
    """Content-minimized failure raised while constructing the one local model."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def construct_transcriber():
    """Construct one local-only transcriber; this path never downloads weights."""
    snapshot = _model_snapshot()
    if not snapshot:
        raise LocalTranscriberUnavailable("model_missing", "Local speech model is not installed.")
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(str(snapshot), device="cpu", compute_type=COMPUTE_TYPE)
    except Exception as exc:
        raise LocalTranscriberUnavailable("model_unavailable", "Local speech model is unavailable.") from exc

    def transcribe(path):
        segments, info = model.transcribe(path, word_timestamps=True)
        events = [{"word": word.word, "start": word.start, "end": word.end, "probability": word.probability}
                  for segment in segments for word in (segment.words or [])]
        return info.language, events, "faster-whisper"
    return transcribe


def install_model() -> dict:
    """Explicit setup action only.  Constructing WhisperModel may download weights."""
    try:
        from faster_whisper import WhisperModel
        model_cache_dir().mkdir(parents=True, exist_ok=True)
        WhisperModel(MODEL_ID, device="cpu", compute_type=COMPUTE_TYPE,
                     download_root=str(model_cache_dir()))
    except Exception as exc:  # setup must be recoverable without leaking paths
        return {"ok": False, "error": "The local speech model could not be prepared.", "code": type(exc).__name__}
    return {"ok": True, **model_status()}


def normalize_tokens(value: str) -> list[str]:
    """NFKC/casefold token normalizer.  Internal apostrophes and hyphens survive."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("’", "'")
    tokens: list[str] = []
    for raw in text.split():
        token = raw.strip("\"'`.,;:!?()[]{}<>/\\|*_~=+…—–")
        if token:
            tokens.append(token)
    return tokens


def validate_passage(value: str) -> tuple[list[str] | None, str | None]:
    tokens = normalize_tokens(value)
    if not 1 <= len(tokens) <= MAX_PASSAGE_TOKENS:
        return None, "Enter a confirmed read-aloud passage with 1 through 3,000 English words."
    if any(not _WORD.fullmatch(token) for token in tokens):
        return None, "The confirmed passage must contain normalized English words only."
    return tokens, None


def passage_digest(tokens: list[str]) -> str:
    return hashlib.sha256(" ".join(tokens).encode("utf-8")).hexdigest()


def align(source: list[str], observed: list[str]) -> list[dict]:
    """Deterministic Levenshtein alignment with exact/sub/omit/insert tie order."""
    rows, cols = len(source), len(observed)
    # Keep costs in two numeric rows; backpointers preserve the existing tie
    # order without allocating a quadratic matrix of Python integers.
    previous = list(range(cols + 1))
    back = bytearray((rows + 1) * (cols + 1))
    for j in range(1, cols + 1): back[j] = 3
    for i in range(1, rows + 1):
        current = [i] + [0] * cols
        back[i * (cols + 1)] = 2
        for j in range(1, cols + 1):
            substitution = previous[j - 1] + (source[i - 1] != observed[j - 1])
            omission, insertion = previous[j] + 1, current[j - 1] + 1
            if substitution <= omission and substitution <= insertion:
                current[j] = substitution; back[i * (cols + 1) + j] = 0 if source[i - 1] == observed[j - 1] else 1
            elif omission <= insertion:
                current[j] = omission; back[i * (cols + 1) + j] = 2
            else:
                current[j] = insertion; back[i * (cols + 1) + j] = 3
        previous = current
    i, j, result = rows, cols, []
    while i or j:
        direction = back[i * (cols + 1) + j]
        if i and j and direction == 0:
            result.append({"kind": "exact", "source_index": i - 1, "observed_index": j - 1}); i -= 1; j -= 1
        elif i and j and direction == 1:
            result.append({"kind": "substitution", "source_index": i - 1, "observed_index": j - 1}); i -= 1; j -= 1
        elif i and direction == 2:
            result.append({"kind": "omission", "source_index": i - 1}); i -= 1
        else:
            result.append({"kind": "insertion", "observed_index": j - 1}); j -= 1
    return list(reversed(result))


def _candidates(operations: list[dict], source: list[str], words: list[dict]) -> tuple[list[dict], bool]:
    candidates = []
    for index, operation in enumerate(operations):
        if operation["kind"] == "exact":
            continue
        observed_index = operation.get("observed_index")
        event = words[observed_index] if observed_index is not None and observed_index < len(words) else {}
        candidate = {"kind": operation["kind"], "expected": source[operation["source_index"]] if "source_index" in operation else "",
                     "observed": event.get("token", ""), "start_seconds": event.get("start_seconds")}
        adjacent_exact = next((candidate for candidate in (operations[index - 1] if index else {},
                                                            operations[index + 1] if index + 1 < len(operations) else {})
                               if candidate.get("kind") == "exact"), None)
        if operation["kind"] == "insertion" and adjacent_exact:
            if source[adjacent_exact["source_index"]] == event.get("token"):
                candidate["candidate"] = "repetition"
        expected_index = operation.get("source_index")
        if expected_index is None and operation["kind"] == "insertion":
            next_exact = next((candidate for candidate in operations[index + 1:]
                               if candidate.get("kind") == "exact"), None)
            expected_index = next_exact.get("source_index") if next_exact else None
        if operation["kind"] != "exact" and expected_index is not None:
            expected = source[expected_index]
            start = (observed_index if observed_index is not None else -1) + 1
            window = [words[n].get("token") for n in range(start, min(len(words), start + 2))]
            if expected in window:
                candidate.setdefault("candidate", "self_correction")
        candidates.append(candidate)
    return candidates[:MAX_DIFFERENCES], len(candidates) > MAX_DIFFERENCES


def make_report(*, canonical_sha256: str, attempt: object, passage: str, duration_seconds: object,
                language: str, word_events: list[dict], model_version: str = "") -> dict:
    source, error = validate_passage(passage)
    if error:
        return {"status": "unavailable", "error_code": "passage_invalid", "error_message": error}
    duration = float(duration_seconds or 0)
    base = {"canonical_sha256": str(canonical_sha256 or ""), "attempt": attempt,
            "passage": " ".join(source), "passage_digest": passage_digest(source),
            "model_id": MODEL_ID, "model_version": model_version, "normalization_version": NORMALIZATION_VERSION,
            "alignment_version": ALIGNMENT_VERSION, "duration_seconds": duration}
    if duration <= 0:
        return {**base, "status": "unavailable", "error_code": "duration_invalid", "error_message": "Recording duration is unavailable."}
    if language != "en":
        return {**base, "status": "needs_review", "uncertainty": ["unsupported_language"], "transcript": "", "word_events": []}
    words = [{"token": normalize_tokens(event.get("word", ""))[0] if normalize_tokens(event.get("word", "")) else "",
              "start_seconds": event.get("start"), "end_seconds": event.get("end"), "confidence": event.get("probability")}
             for event in word_events]
    words = [word for word in words if word["token"]]
    if not words:
        return {**base, "status": "needs_review", "uncertainty": ["empty_or_unintelligible"], "transcript": "", "word_events": []}
    operations = align(source, [word["token"] for word in words])
    exact = sum(operation["kind"] == "exact" for operation in operations)
    candidates, truncated = _candidates(operations, source, words)
    uncertainty = []
    if any((word.get("confidence") is not None and float(word["confidence"]) < CONFIDENCE_FLOOR) for word in words):
        uncertainty.append("low_confidence")
    if truncated: uncertainty.append("difference_candidates_truncated")
    return {**base, "status": "needs_review" if uncertainty else "complete", "transcript": " ".join(word["token"] for word in words),
            "word_events": words, "metrics": {"source_words": len(source), "exact_matched_words": exact,
            "accuracy": exact / len(source), "wcpm": exact / (duration / 60)}, "uncertainty": uncertainty,
            "difference_candidates": candidates, "difference_candidates_truncated": truncated}


def analyze_recording(record: dict, passage: str, *, transcribe=None) -> dict:
    """Analyze an already-finalized canonical recording; never downloads at start."""
    if not record.get("canonical_path") or not record.get("canonical_sha256"):
        return {"status": "unavailable", "error_code": "canonical_audio_missing", "error_message": "Canonical local audio is unavailable."}
    try:
        if transcribe is None:
            transcribe = construct_transcriber()
        language, events, version = transcribe(record["canonical_path"])
        return make_report(canonical_sha256=record["canonical_sha256"], attempt=record.get("attempt", 1), passage=passage,
                           duration_seconds=record.get("duration_seconds"), language=language, word_events=events, model_version=version)
    except LocalTranscriberUnavailable as exc:
        return {"status": "unavailable", "error_code": exc.code, "error_message": exc.message}
    except Exception:
        return {"status": "unavailable", "error_code": "transcription_failed", "error_message": "Local transcription could not be completed."}


def reusable(report: dict, record: dict, passage: str) -> bool:
    tokens, error = validate_passage(passage)
    return bool(not error and isinstance(report, dict) and report.get("canonical_sha256") == record.get("canonical_sha256")
                and report.get("attempt") == record.get("attempt", 1) and report.get("passage_digest") == passage_digest(tokens)
                and report.get("model_id") == MODEL_ID and report.get("normalization_version") == NORMALIZATION_VERSION
                and report.get("alignment_version") == ALIGNMENT_VERSION)


def review_projection(report: dict) -> dict:
    """Whitelist the browser view; private word events stay in the session only."""
    allowed = ("status", "error_code", "error_message", "passage", "transcript", "metrics", "uncertainty",
               "difference_candidates", "difference_candidates_truncated", "duration_seconds")
    return {key: report[key] for key in allowed if key in report}


def project_session(session: dict) -> dict:
    view = dict(session)
    students = []
    for student in session.get("students") or []:
        student_view = dict(student)
        student_view["attachments"] = [dict(item) for item in student.get("attachments") or []]
        for item in student_view["attachments"]:
            item.pop("oral_reading_private", None)
        students.append(student_view)
    view["students"] = students
    return view
