"""Regression test for the routines scheduler.

_run_routines_bg used to skip every routine with custom=True, contradicting
api/webui/README.md's explicit claim that custom routines get "the same
three triggers ... as built-ins ... no parallel path." There was no test
covering the scheduler at all, built-in or custom, before this file.
"""
from api.platform_services import config
from api.webui.routes import routines


def _fake_routine_defs(custom):
    return {
        "fake_routine": {
            "label": "Fake Routine",
            "writes": False,
            "default": {"enabled": False, "every_hours": 24, "params": {}},
            "custom": custom,
        }
    }


def test_scheduler_runs_a_due_custom_routine(monkeypatch):
    calls = []

    def fake_runner(params):
        calls.append(params)
        return {"ok": True, "summary": "ran"}

    monkeypatch.setattr(routines, "_ROUTINE_DEFS", _fake_routine_defs(custom=True))
    monkeypatch.setattr(routines, "_ROUTINE_RUNNERS", {"fake_routine": fake_runner})
    config.set_routine_state("fake_routine", {"enabled": True})

    routines._run_routines_bg()

    assert len(calls) == 1
    state = config.get_routine_states()["fake_routine"]
    assert state["last_run"]
    assert state["last_summary"] == "ran"


def test_scheduler_skips_a_disabled_custom_routine(monkeypatch):
    calls = []

    def fake_runner(params):
        calls.append(params)
        return {"ok": True, "summary": "ran"}

    monkeypatch.setattr(routines, "_ROUTINE_DEFS", _fake_routine_defs(custom=True))
    monkeypatch.setattr(routines, "_ROUTINE_RUNNERS", {"fake_routine": fake_runner})
    config.set_routine_state("fake_routine", {"enabled": False})

    routines._run_routines_bg()

    assert calls == []
    assert "fake_routine" not in config.get_routine_states() or \
        "last_run" not in config.get_routine_states()["fake_routine"]


def test_scheduler_runs_a_due_builtin_routine_unchanged(monkeypatch):
    calls = []

    def fake_runner(params):
        calls.append(params)
        return {"ok": True, "summary": "ran"}

    monkeypatch.setattr(routines, "_ROUTINE_DEFS", _fake_routine_defs(custom=False))
    monkeypatch.setattr(routines, "_ROUTINE_RUNNERS", {"fake_routine": fake_runner})
    config.set_routine_state("fake_routine", {"enabled": True})

    routines._run_routines_bg()

    assert len(calls) == 1
