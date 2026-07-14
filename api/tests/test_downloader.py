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

    by_assignment = tmp_path / "Assignments" / "Narrative One — 42"
    amy = by_assignment / "Student Work" / "Learner, Amy — 101" / "Attempt 1"
    ben = by_assignment / "Student Work" / "Writer, Ben The — 102" / "Attempt 1"

    assert (amy / "Written Response.txt").exists()
    assert (amy / "Submitted URL.txt").exists()
    assert (amy / "final draft.docx").exists()
    assert (ben / "Written Response.txt").exists()
    assert (tmp_path / "Course Information.txt").exists() is False
    assert (by_assignment / "Assignment Information.txt").exists()

    with open(by_assignment / "_index.csv", newline="", encoding="utf-8") as f:
        rows = {row["name"]: row for row in csv.DictReader(f)}
    assert rows["Amy Learner"]["files"] == (
        "Written Response.txt; Submitted URL.txt; final draft.docx"
    )
    assert rows["Ben The Writer"]["files"] == "Written Response.txt"


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

    asgn = tmp_path / "Assignments" / "Reflection — 77"
    assert (asgn / "Student Work" / "Learner, Amy — 201" / "Attempt 1" / "Written Response.txt").exists()
    assert (asgn / "Student Work" / "Learner, Alex — 202" / "Attempt 1" / "Written Response.txt").exists()

