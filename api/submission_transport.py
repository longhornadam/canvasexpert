"""Small read-only transport helpers retained for reports and portfolios."""
import os

import requests


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
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    with open(destination, "wb") as output:
        for chunk in response.iter_content(chunk_size=16_384):
            if chunk:
                output.write(chunk)
