"""The store round-trips, and every CLI runs end to end on the fixtures.

These go through a real Repository on a tmp_path root with a MappingResolver,
so no vault and no workspace are involved. That is the point: the substrate has
to be exercisable offline, or nobody will exercise it.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from api.dailywriting.cli import calibrate as cli_calibrate
from api.dailywriting.cli import digest as cli_digest
from api.dailywriting.cli import ingest as cli_ingest
from api.dailywriting.cli import regen_profiles as cli_regen
from api.dailywriting.cli import score as cli_score
from api.dailywriting.core.models import ProfileFieldError
from api.dailywriting.fixtures import loader
from api.dailywriting.store import codec
from api.dailywriting.store.repo import Repository

SECTION = "ELA7-PREAP-2A"


@pytest.fixture
def repository(tmp_path) -> Repository:
    return Repository(tmp_path / "store", resolver=loader.resolver(), vault=None)


@pytest.fixture
def identity_map(tmp_path):
    path = tmp_path / "identity.json"
    path.write_text(json.dumps({
        entry["canvas_id"]: entry["pseudonym"]
        for entry in loader.vault_entries()}), encoding="utf-8")
    return path


@pytest.fixture
def day_file(tmp_path):
    """An ingest input file built from the single fixtures."""
    reps = [codec.rep_to_dict(loader.rep(rep_id)) for rep_id in loader.rep_ids()]
    submissions = []
    for number in loader.single_numbers():
        raw = loader.single(number)
        submissions.append({
            "submission_id": raw["submission_id"],
            "rep_id": raw["rep_id"],
            "pseudonym": loader.pseudonym_for(raw["canvas_id"]),
            "submitted_at": raw["submitted_at"],
            "text": raw["text"],
        })
    path = tmp_path / "day.json"
    path.write_text(json.dumps({"reps": reps, "submissions": submissions}),
                    encoding="utf-8")
    return path


def _cli(module, argv, capsys) -> str:
    assert module.main(argv) == 0
    return capsys.readouterr().out


# --- store ------------------------------------------------------------------


def test_records_round_trip_through_the_store(repository, ingest_fixture):
    result = ingest_fixture(6)
    pseudonym = result.submission.pseudonym_id

    repository.put_rep(loader.rep(result.submission.rep_id))
    repository.append_submission(result.submission)
    repository.append_score(result.score, pseudonym)
    repository.append_observations(result.observations)

    window = (date(2026, 10, 1), date(2026, 10, 31))
    stored = repository.submissions_in_window(pseudonym, *window)
    assert [s.submission_id for s in stored] == [result.submission.submission_id]
    assert stored[0].raw_text == result.submission.raw_text
    assert stored[0].segments == result.submission.segments
    assert stored[0].student_word_count == result.submission.student_word_count

    scores = repository.scores_for([result.submission.submission_id])
    assert scores[result.submission.submission_id] == result.score

    observations = repository.observations_in_window(pseudonym, *window)
    assert {o.obs_id for o in observations} == {o.obs_id
                                               for o in result.observations}
    assert repository.read_rep(result.submission.rep_id).prompt_text


def test_on_disk_records_are_keyed_by_canvas_id_not_pseudonym(
        repository, ingest_fixture):
    """The durable key survives a teacher regenerating a pseudonym."""
    result = ingest_fixture(1)
    repository.append_submission(result.submission)
    written = json.loads(
        (repository.root / "submissions" / "2026-09.json").read_text("utf-8"))
    record = written["submissions"][0]
    assert record["canvas_id"] == "990001"
    assert "pseudonym" not in json.dumps(record)
    assert "Sparky" not in json.dumps(record)


def test_re_ingest_is_idempotent_while_the_file_stays_append_only(
        repository, ingest_fixture):
    result = ingest_fixture(1)
    for _ in range(3):
        repository.append_submission(result.submission)
        repository.append_observations(result.observations)

    raw = json.loads(
        (repository.root / "submissions" / "2026-09.json").read_text("utf-8"))
    assert len(raw["submissions"]) == 3, "the document should be append-only"

    stored = repository.submissions_in_window(
        result.submission.pseudonym_id, date(2026, 9, 1), date(2026, 9, 30))
    assert len(stored) == 1, "readers keep the latest entry for an id"


def test_a_stored_profile_with_a_non_writing_field_is_refused_on_read(
        repository, tmp_path):
    """INV-5 holds on the way in from disk, not only at construction."""
    path = repository.root / "profiles" / "990001.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema": 1, "canvas_id": "990001",
        "generated_at": "2026-11-14T06:00:00+00:00",
        "window_start": "2026-10-17", "window_end": "2026-11-14",
        "tier": 1, "per_criterion_rate": {}, "active_patterns": [],
        "open_directives": [], "best_piece": None, "next_focus": "",
        "ready_for_tier_advance": False,
        "behavior_notes": "talks during independent work",
    }), encoding="utf-8")
    with pytest.raises(ProfileFieldError):
        repository.read_profile("Sparky McGee")


def test_weekly_totals_expose_daily_and_aggregate_without_choosing_a_rollup(
        repository, ingest_fixture):
    result = ingest_fixture(1)
    pseudonym = result.submission.pseudonym_id
    repository.append_submission(result.submission)
    repository.append_score(result.score, pseudonym)

    totals = repository.weekly_totals(pseudonym, date(2026, 9, 14),
                                      date(2026, 9, 18))
    assert totals["reps_submitted"] == 1
    assert totals["possible"] == result.score.possible
    assert totals["daily"][0]["rep_id"] == "rep_t1_phones"


# --- CLI --------------------------------------------------------------------


def test_ingest_cli_dry_run_writes_nothing(day_file, identity_map, tmp_path,
                                           capsys):
    root = tmp_path / "store"
    out = _cli(cli_ingest, ["--input", str(day_file), "--dry-run",
                            "--store-root", str(root),
                            "--identity-map", str(identity_map)], capsys)
    assert "Dry run: nothing was written." in out
    assert not root.exists()


def test_ingest_then_score_then_profiles_then_digest_then_calibrate(
        day_file, identity_map, tmp_path, capsys):
    root = tmp_path / "store"
    store_args = ["--store-root", str(root), "--identity-map", str(identity_map)]
    students = [entry["pseudonym"] for entry in loader.vault_entries()]

    out = _cli(cli_ingest, ["--input", str(day_file)] + store_args, capsys)
    assert "submission(s) processed" in out
    # Fixture 5 is the empty stem: it must be reported, not silently zeroed.
    assert "no_student_text" in out
    assert "empty_stem_blank" in out

    out = _cli(cli_score, ["--from", "2026-09-01", "--to", "2026-12-31",
                           "--students", *students] + store_args, capsys)
    assert "re-scored" in out
    assert "skipped" in out

    out = _cli(cli_regen, ["--as-of", "2026-11-14",
                           "--students", *students] + store_args, capsys)
    assert "profile(s) regenerated" in out
    assert "next:" in out

    out = _cli(cli_digest, ["--section", SECTION,
                            "--week-start", "2026-10-26",
                            "--week-end", "2026-10-30",
                            "--students", *students] + store_args, capsys)
    assert "Top failure modes" in out
    assert "Per-criterion class rate" in out
    # The Goodhart case has to be visible to the teacher even though the
    # checker passed it.
    assert "commentary_formulaic" in out

    out = _cli(cli_calibrate, ["sample", "--from", "2026-09-01",
                               "--to", "2026-12-31", "--sample-id", "test-01",
                               "--size", "6", "--students", *students]
               + store_args, capsys)
    assert "score bands" in out
    assert "Machine scores are not in this sample" in out


def test_calibration_sample_on_disk_carries_no_machine_scores(
        day_file, identity_map, tmp_path, capsys):
    root = tmp_path / "store"
    store_args = ["--store-root", str(root), "--identity-map", str(identity_map)]
    _cli(cli_ingest, ["--input", str(day_file)] + store_args, capsys)
    _cli(cli_calibrate, ["sample", "--from", "2026-09-01", "--to", "2026-12-31",
                         "--sample-id", "test-02", "--size", "6"]
         + store_args, capsys)

    written = json.loads(
        (root / "calibration" / "test-02.json").read_text("utf-8"))
    serialized = json.dumps(written)
    assert "per_item" not in serialized
    assert "total" not in serialized
    assert written["items"]


def test_calibration_agreement_reports_per_criterion_and_names_disagreements(
        day_file, identity_map, tmp_path, capsys):
    root = tmp_path / "store"
    store_args = ["--store-root", str(root), "--identity-map", str(identity_map)]
    _cli(cli_ingest, ["--input", str(day_file)] + store_args, capsys)
    _cli(cli_calibrate, ["sample", "--from", "2026-09-01", "--to", "2026-12-31",
                         "--sample-id", "test-03", "--size", "6"]
         + store_args, capsys)

    repository = Repository(root, resolver=loader.resolver(), vault=None)
    sample = repository.read_calibration("test-03")
    machine = repository.scores_for(sample.submission_ids)

    # Score the sample blind, disagreeing on purpose about one criterion.
    answers = {"scores": {}}
    for item in sample.items:
        score = machine[item.submission_id]
        marks = {item_id: bool(result.met)
                 for item_id, result in score.per_item.items()}
        if "arguable" in marks:
            marks["arguable"] = not marks["arguable"]
        answers["scores"][item.submission_id] = marks
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(answers), encoding="utf-8")

    out = _cli(cli_calibrate, ["agreement", "--sample-id", "test-03",
                               "--answers", str(answers_path)] + store_args,
               capsys)
    assert "overall agreement" in out
    assert "Disagreements" in out
    assert "arguable" in out
    assert "0%" in out, "the criterion we inverted should show zero agreement"


def test_a_command_reports_a_bad_date_without_a_traceback(identity_map, tmp_path,
                                                          capsys):
    from api.dailywriting.cli import _common

    code = _common.run(lambda argv: cli_regen.main(argv), [
        "--as-of", "the-fourteenth", "--store-root", str(tmp_path / "store"),
        "--identity-map", str(identity_map)])
    assert code == 2
    assert "is not a date" in capsys.readouterr().out


def test_digest_says_so_when_it_has_no_roster(day_file, identity_map, tmp_path,
                                              capsys):
    """A short missing-work list must not read as a complete one."""
    root = tmp_path / "store"
    store_args = ["--store-root", str(root), "--identity-map", str(identity_map)]
    _cli(cli_ingest, ["--input", str(day_file)] + store_args, capsys)
    out = _cli(cli_digest, ["--section", SECTION, "--week-start", "2026-10-26",
                            "--week-end", "2026-10-30"] + store_args, capsys)
    assert "No roster supplied" in out
    assert "--students-file" in out
