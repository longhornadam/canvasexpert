"""Ignore and snooze operations keyed by fingerprint and material version."""

from __future__ import annotations

from datetime import datetime, timezone

from . import storage
from .models import validate_job, validate_suppressions


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)


def _put(job: dict, mode: str, until: str = "") -> dict:
    validate_job(job)
    document = storage.read_suppressions()
    identity = (job["fingerprint"], job["material_version"])
    document["items"] = [
        item for item in document["items"]
        if (item["fingerprint"], item["material_version"]) != identity
    ]
    document["items"].append({
        "fingerprint": job["fingerprint"],
        "material_version": job["material_version"],
        "mode": mode,
        "until": until,
        "updated_at": _iso(_now()),
    })
    return storage.write_suppressions(document)


def ignore(job: dict) -> dict:
    return _put(job, "ignored")


def snooze(job: dict, until: str) -> dict:
    validate_job(job)
    if not isinstance(until, str):
        raise ValueError("until must be ISO-8601")
    try:
        parsed = _parse(until)
    except (TypeError, ValueError) as exc:
        raise ValueError("until must be ISO-8601") from exc
    if parsed <= _now():
        raise ValueError("until must be in the future")
    return _put(job, "snoozed", _iso(parsed))


def clear_for_material_change(job: dict) -> dict:
    validate_job(job)
    document = storage.read_suppressions()
    document["items"] = [
        item for item in document["items"] if item["fingerprint"] != job["fingerprint"]
    ]
    return storage.write_suppressions(document)


def is_suppressed(job: dict, now: datetime | None = None) -> bool:
    validate_job(job)
    document = storage.read_suppressions()
    validate_suppressions(document)
    current = now or _now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    for item in document["items"]:
        if (item["fingerprint"], item["material_version"]) != (job["fingerprint"], job["material_version"]):
            continue
        if item["mode"] == "ignored":
            return True
        if item["mode"] == "snoozed" and item["until"]:
            return _parse(item["until"]) > current
    return False
