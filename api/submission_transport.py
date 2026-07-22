"""Small read-only transport helpers retained for reports and portfolios."""
import os

import requests

from api.webui import workspace


def get_all_pages(session, url, params=None):
    results, params = [], dict(params or {})
    params.setdefault("per_page", 100)
    while url:
        response = session.get(url, params=params, timeout=30)
        response.raise_for_status()
        results.extend(response.json())
        params, url = {}, None
        for part in response.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break
    return results


def download_binary(session, url, destination):
    response = session.get(url, stream=True, allow_redirects=True, timeout=120)
    response.raise_for_status()
    os.makedirs(workspace.extended_path(os.path.dirname(destination)), exist_ok=True)
    with open(workspace.extended_path(destination), "wb") as output:
        for chunk in response.iter_content(chunk_size=16_384):
            if chunk:
                output.write(chunk)


def fetch_submission(session, base, course_id, assignment_id, user_id):
    """Fetch exactly one student's one submission (for its current ``attachments``).

    A single, focused Canvas call — never a whole-course fetch. Returns ``None`` on
    any non-200 response or transport failure rather than raising, so a missing or
    failed focused fetch degrades to "no attachments found" for that one work
    sample instead of aborting the whole report.
    """
    url = f"{base}/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/{user_id}"
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None
