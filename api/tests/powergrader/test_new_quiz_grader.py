"""Signed grader launch contracts through the actual HTTP acquisition chain."""
from urllib.parse import parse_qsl, urlencode, urlparse

import pytest

from api.powergrader import new_quiz_grader


@pytest.mark.parametrize("path, options", [
    ("/courses/111/external_tools/retrieve", []),
    ("/courses/111/external_tools/retrieve", [("new_quizzes_native_experience_sessionless", "true"),
                                            ("new_quizzes_native_experience_sessionless", "")]),
    ("/other-preview", [("new_quizzes_native_experience_sessionless", "true")]),
])
def test_signed_context_preserves_launch_arguments_and_selects_web_form(_signed_grader_http, path, options):
    retained = [("url", "https://quiz.invalid/launch?student=one&empty=&encoded=%2B"),
                ("blank", ""), ("repeat", "one"), ("repeat", "two")]
    preview_url = "https://canvas.invalid" + path + "?" + urlencode(retained + options) + "#preview"
    http, calls = _signed_grader_http(preview_url)

    context = new_quiz_grader._signed_context(canvas_base="https://canvas.invalid", token="synthetic-pat",
                                            assignment_id="synthetic-assignment", user_id="synthetic-student",
                                            http_session=http)

    assert context == (http, "https://quiz.invalid", {"Authorization": "Bearer synthetic-launch-token"},
                       "synthetic-participant")
    assert [call[0] for call in calls] == ["GET", "GET", "POST", "GET", "POST"]
    requested = urlparse(calls[3][1])
    expected_options = [("new_quizzes_native_experience_sessionless", "false")] if path.endswith("/external_tools/retrieve") else options
    assert parse_qsl(requested.query, keep_blank_values=True) == retained + expected_options
    assert requested.path == path
    assert requested.fragment == "preview"
    assert calls[4][1] == "https://quiz.invalid/signed"
    assert calls[4][2]["data"] == {"participant_session_id": "synthetic-participant", "signature": "synthetic-signature"}
    assert "headers" not in calls[4][2]


def test_signed_context_rejects_missing_form_without_native_fallback(_signed_grader_http):
    http, calls = _signed_grader_http("https://canvas.invalid/courses/111/external_tools/retrieve", launch_form=False)

    with pytest.raises(new_quiz_grader.GraderError, match="^signed_launch_shape$"):
        new_quiz_grader._signed_context(canvas_base="https://canvas.invalid", token="synthetic-pat",
                                       assignment_id="synthetic-assignment", user_id="synthetic-student",
                                       http_session=http)
    assert len(calls) == 4
    assert calls[-1][0] == "GET"
