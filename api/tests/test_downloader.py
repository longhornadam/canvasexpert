import csv

from api import downloader


class _Response:
    def __init__(self, data=None, content=b""):
        self._data = data
        self._content = content
        self.headers = {}

    def json(self):
        return self._data

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield self._content


class _Session:
    def __init__(self, submissions):
        self.submissions = submissions

    def get(self, url, **kwargs):
        if url.endswith("/submissions"):
            return _Response(self.submissions)
        return _Response(content=b"downloaded bytes")


def test_download_assignment_uses_assignment_then_student_suffix(tmp_path):
    assignment = {
        "id": "42",
        "name": "Narrative One",
        "submission_types": ["online_text_entry", "online_url", "online_upload"],
        "points_possible": 10,
    }
    submissions = [
        {
            "user_id": "101",
            "user": {"name": "Amy Learner"},
            "score": 9,
            "workflow_state": "submitted",
            "submitted_at": "2026-02-03T14:05:00Z",
            "body": "<p>My response</p>",
            "url": "https://example.invalid/work",
            "attachments": [
                {"filename": "final draft.docx", "url": "https://files.invalid/101"}
            ],
        },
        {
            "user_id": "102",
            "user": {"name": "Ben The Writer", "sortable_name": "Writer, Ben The"},
            "score": 8,
            "workflow_state": "submitted",
            "submitted_at": "2026-02-03T15:05:00Z",
            "body": "<p>Another response</p>",
        },
    ]

    list(downloader._download_assignment(
        _Session(submissions),
        "https://canvas.invalid",
        "7",
        assignment,
        str(tmp_path),
    ))

    by_assignment = tmp_path / "by_assignment" / "Narrative One"
    by_student = tmp_path / "by_student"

    expected_assignment_files = {
        "Narrative One - A Learner.html",
        "Narrative One - A Learner - URL.txt",
        "Narrative One - A Learner - final draft.docx",
        "Narrative One - B Writer.html",
    }
    assert expected_assignment_files <= {p.name for p in by_assignment.iterdir()}
    assert not (by_assignment / "Amy Learner.html").exists()

    assert (by_student / "Amy Learner" / "Narrative One - A Learner.html").exists()
    assert (by_student / "Amy Learner" / "Narrative One - A Learner - URL.txt").exists()
    assert (by_student / "Amy Learner" / "Narrative One - A Learner - final draft.docx").exists()
    assert (by_student / "Ben The Writer" / "Narrative One - B Writer.html").exists()

    with open(by_assignment / "_index.csv", newline="", encoding="utf-8") as f:
        rows = {row["name"]: row for row in csv.DictReader(f)}
    assert rows["Amy Learner"]["files"] == (
        "Narrative One - A Learner.html; "
        "Narrative One - A Learner - URL.txt; "
        "Narrative One - A Learner - final draft.docx"
    )
    assert rows["Ben The Writer"]["files"] == "Narrative One - B Writer.html"


def test_matching_student_suffixes_do_not_overwrite_files(tmp_path):
    assignment = {
        "id": "77",
        "name": "Reflection",
        "submission_types": ["online_text_entry"],
        "points_possible": 5,
    }
    submissions = [
        {
            "user_id": "201",
            "user": {"name": "Amy Learner"},
            "workflow_state": "submitted",
            "body": "First response",
        },
        {
            "user_id": "202",
            "user": {"name": "Alex Learner"},
            "workflow_state": "submitted",
            "body": "Second response",
        },
    ]

    list(downloader._download_assignment(
        _Session(submissions),
        "https://canvas.invalid",
        "7",
        assignment,
        str(tmp_path),
    ))

    by_assignment = tmp_path / "by_assignment" / "Reflection"
    assert (by_assignment / "Reflection - A Learner.html").exists()
    assert (by_assignment / "Reflection - A Learner (2).html").exists()

