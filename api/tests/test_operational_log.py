"""Tests for the rotating traceback log (B3) added beside operations.jsonl.

Unlike emit()'s validated JSONL records, this file is raw text with no key
allowlist -- these tests cover its own contract (best-effort, stable path,
round-trips through tail_traceback_text), not any particular caller.
"""
from api import operational_log


def test_write_traceback_then_tail_round_trips(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    operational_log.write_traceback("Traceback (most recent call last):\n  boom\nValueError: kaboom\n")
    text = operational_log.tail_traceback_text()
    assert "ValueError: kaboom" in text


def test_tail_traceback_text_is_empty_when_no_file_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    assert operational_log.tail_traceback_text() == ""


def test_write_traceback_is_a_noop_on_empty_text(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    operational_log.write_traceback("")
    assert operational_log.tail_traceback_text() == ""


def test_write_traceback_never_raises_on_a_broken_path(tmp_path, monkeypatch):
    """Matches emit()'s own never-raise contract: diagnostics must not be
    able to break the caller, even if the log directory can't be created."""
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("x", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(blocking_file))
    operational_log.write_traceback("this must not raise")


def test_errors_log_is_separate_from_operations_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    operational_log.emit("diagnostics.health", "ok")
    operational_log.write_traceback("a raw traceback, not a JSON record")
    assert operational_log._log_path().name == "operations.jsonl"
    assert operational_log._error_log_path().name == "errors.log"
    assert operational_log._log_path() != operational_log._error_log_path()
    operations_content = operational_log._log_path().read_text(encoding="utf-8")
    assert "a raw traceback" not in operations_content
