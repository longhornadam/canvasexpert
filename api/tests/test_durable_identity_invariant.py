"""One rule, in one place: a durable artifact must not key a student by pseudonym.

A pseudonym is a label the teacher can change at any time, from the Students
page or the Name Manager. Anything that stores it as the identity of a record
silently loses that record on the next rename. Anything that stores a stable
Canvas id and resolves the label when reading does not.

That was not a hypothetical. DataForge assessment history stored the pseudonym
as a snapshot row's only identity, so a mid-year rename orphaned the student's
scores and split their growth record in two, with no error anywhere.

So, for every store that durably holds student work:

* persist the **canvas_id**, and resolve the current pseudonym at read;
* if the stored form is prose a teacher reads, the pseudonym may stay inside
  the text (`api/dailywriting/core/scrub.py` measured and rejected redacting a
  name out of student writing), but then a rename has to rewrite it, which is
  what `api/pseudonym_rename.py` coordinates;
* never let the canvas_id reach an artifact that leaves the machine. The
  published standards profile is proven pseudonym-only by
  `api/tests/dataforge/test_shared_publish.py`.

Adding a third store means adding it to this test and to
`api/pseudonym_rename.py`. If this test fails, the fix is almost never to
change the assertion.
"""
import json
from datetime import date, datetime, timezone

from api.dailywriting.core import ingest
from api.dailywriting.core.models import AssignmentContext
from api.dailywriting.store import codec
from api.dataforge import history_store

PSEUDONYM = "Sparky McGee"
CANVAS_ID = "canvas-77"


class _Paths:
    def __init__(self, tmp_path):
        self.history_dir = tmp_path / "history"


def test_writing_evidence_persists_the_canvas_id_not_the_pseudonym():
    """The pseudonym stays inside the prose on purpose, but it must not be the
    key: `Repository` resolves it to a canvas_id on write and back to the
    current pseudonym on read."""
    submission = ingest.ingest(
        submission_id="sub-1", rep_id="rep-1", pseudonym_id=PSEUDONYM,
        submitted_at=datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc),
        text="One paragraph about a favorite hobby.",
        context=AssignmentContext(
            rep_id="rep-1", date=date(2026, 9, 1),
            prompt_text="Write one paragraph about a favorite hobby."),
    )
    document = codec.submission_to_dict(submission, canvas_id=CANVAS_ID)

    assert document["canvas_id"] == CANVAS_ID
    assert PSEUDONYM not in document, "the pseudonym must not be a stored key"
    assert not any(value == PSEUDONYM for value in document.values()), (
        "the pseudonym must not be a stored field either; it belongs only "
        "inside the prose, where a rename rewrites it"
    )


def test_assessment_history_persists_the_canvas_id_for_every_named_row(tmp_path):
    """A snapshot row's identity is its canvas_id. The stored `n` is a stale
    label by design: `build_profile` groups by canvas_id and re-resolves the
    name, so a rename is reflected without touching the file."""
    paths = _Paths(tmp_path)
    history_store.save_snapshot(paths, {
        "descriptive": "45 Synthetic Benchmark",
        "assessment_name": "Synthetic Benchmark",
        "grade": "7", "type": "STAAR", "breakdown_type": "learning_standard",
        "standards": [{"code": "7.9(D)"}],
        "tier_students": [
            {"n": PSEUDONYM, "canvas_id": CANVAS_ID, "pct": 82.0, "missed": {}},
            # A prior-year student the vault never linked: numbers kept,
            # identity dropped, so no canvas_id to store.
            {"n": "", "canvas_id": "", "pct": 41.0, "missed": {}},
        ],
    })

    saved = next(paths.history_dir.glob("*.json"))
    students = json.loads(saved.read_text(encoding="utf-8"))["students"]
    named = [row for row in students if row.get("n")]
    assert named, "the fixture must contain at least one named row"
    for row in named:
        assert "canvas_id" in row, (
            "a named snapshot row without a canvas_id cannot survive a rename"
        )
    assert named[0]["canvas_id"] == CANVAS_ID
