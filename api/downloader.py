"""Canvas submission downloader.

Raw work has one canonical copy in a course-first tree.  Student-first views
belong to derived reports; this module never mirrors bytes into a second tree.
"""

import csv
import os
import re

import requests

try:
    from webui import workspace
except ModuleNotFoundError:  # package/test context
    from api.webui import workspace


def safe_name(s: str, max_len: int = 80) -> str:
    return workspace.safe_component(s, max_len=max_len)


def _name_parts(raw_name):
    raw = (raw_name or "").strip()
    if not raw:
        return "", ""
    if "," in raw:
        last, first = raw.split(",", 1)
        first = first.strip().split()
        return (first[0] if first else ""), last.strip()
    parts = raw.split()
    if len(parts) >= 2:
        return parts[0], parts[-1]
    return "", ""


def _student_display_name(user, fallback_user_id=None):
    user = user or {}
    sortable = (user.get("sortable_name") or "").strip()
    if sortable:
        return sortable
    raw = (user.get("name") or "").strip()
    first, last = _name_parts(raw)
    return f"{last}, {first}" if first and last else (raw or f"user_{fallback_user_id}")


def _student_file_tag(user, fallback_user_id=None):
    user = user or {}
    for key in ("sortable_name", "name"):
        first, last = _name_parts(user.get(key))
        if first and last:
            return safe_name(f"{first[:1].upper()} {last}", 40)
    fallback = user.get("name") or user.get("sortable_name") or f"user_{fallback_user_id}"
    return safe_name(fallback, 40)


def _assignment_student_stem(assignment_name, student_tag, max_len=110):
    tag = safe_name(student_tag, 40)
    sep = " - "
    max_assignment = max(1, max_len - len(sep) - len(tag))
    assignment_part = safe_name(assignment_name, max_assignment)
    return f"{assignment_part}{sep}{tag}"


def _work_filename(assignment_name, student_tag, ext="", detail=""):
    stem = _assignment_student_stem(assignment_name, student_tag)
    if detail:
        stem += " - " + safe_name(detail, 40)
    return stem + (ext or "")


def _reserve_filename(filename, used):
    stem, ext = os.path.splitext(filename)
    if isinstance(used, dict):
        directory = used.get("__directory__", "")
        names = used.setdefault("__names__", set())
    else:
        directory = ""
        names = used
    candidate = filename
    n = 2
    while candidate in names or (directory and os.path.exists(os.path.join(directory, candidate))):
        candidate = f"{stem} ({n}){ext}"
        n += 1
    names.add(candidate)
    return candidate


def _get_all_pages(session, url, params=None):
    results, params = [], dict(params or {})
    params.setdefault("per_page", 100)
    while url:
        r = session.get(url, params=params, timeout=30)
        r.raise_for_status()
        results.extend(r.json())
        params = {}
        url = None
        for part in r.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break
    return results


def _write_text_file(path, student, assignment, score, submitted_at, body):
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            f"Student:    {student}\n"
            f"Assignment: {assignment}\n"
            f"Score:      {score}\n"
            f"Submitted:  {submitted_at}\n\n"
        )
        f.write(body)


def _write_info(path, title, values):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{title}\n{'=' * len(title)}\n\n")
        for key, value in values:
            f.write(f"{key}: {value}\n")


def _download_binary(session, url, dest):
    r = session.get(url, stream=True, allow_redirects=True, timeout=120)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=16_384):
            f.write(chunk)


def _course_dir(download_root, course_name, course_id):
    """Resolve the course folder, preserving an explicitly selected custom root."""
    configured = os.path.abspath(str(download_root))
    workspace_root = workspace.workspace_root()
    if workspace_root and configured == os.path.abspath(workspace_root):
        return workspace.course_folder(course_name, course_id)
    return os.path.join(configured, workspace.named_id_folder(course_name, course_id))


DOWNLOADABLE_TYPES = {"online_text_entry", "online_upload", "discussion_topic", "online_url"}


def _download_assignment(session, canvas_base, course_id, assignment, course_dir,
                         *, course_name="", course_info=None):
    """Yield progress while writing one assignment-first canonical subtree."""
    asgn_id = str(assignment["id"])
    asgn_name = assignment.get("name", f"assignment_{asgn_id}")
    sub_types = set(assignment.get("submission_types") or [])
    points = assignment.get("points_possible", "?")

    yield f"  ▶ {asgn_name}  ({', '.join(sub_types) or 'none'})  [{points} pts]"
    if not (sub_types & DOWNLOADABLE_TYPES):
        yield "      – skipped (type not downloadable)"
        return

    # course_dir is already the canonical course folder.  A direct call in a
    # unit test can provide a temporary course root and gets the same shape.
    assignment_dir = os.path.join(
        course_dir, "Assignments", workspace.named_id_folder(asgn_name, asgn_id)
    )
    student_work_root = os.path.join(assignment_dir, "Student Work")
    os.makedirs(student_work_root, exist_ok=True)
    _write_info(
        os.path.join(assignment_dir, "Assignment Information.txt"),
        "Assignment Information",
        [("Current Canvas name", asgn_name), ("Canvas assignment ID", asgn_id),
         ("Points possible", points), ("Submission types", ", ".join(sorted(sub_types)))],
    )
    if course_info:
        _write_info(
            os.path.join(course_dir, "Course Information.txt"),
            "Course Information",
            course_info,
        )

    subs = _get_all_pages(
        session,
        f"{canvas_base}/api/v1/courses/{course_id}/assignments/{asgn_id}/submissions",
        {"include[]": "user"},
    )

    index_rows = []
    n_written = 0
    for sub in subs:
        user = sub.get("user") or {}
        uid = str(sub.get("user_id") or "unknown")
        raw_name = user.get("name") or user.get("sortable_name") or f"user_{uid}"
        student_name = _student_display_name(user, uid)
        score = sub.get("score", "")
        state = sub.get("workflow_state", "")
        sub_at = (sub.get("submitted_at") or "")[:19].replace("T", " ")
        attempt = sub.get("attempt") or 1
        attempt_dir = os.path.join(
            student_work_root, workspace.named_id_folder(student_name, uid, max_len=120),
            f"Attempt {workspace.safe_id(attempt, '1')}",
        )
        os.makedirs(attempt_dir, exist_ok=True)
        files_ok = []
        used = {"__directory__": attempt_dir}

        body = (sub.get("body") or "").strip()
        if body:
            fname = "Written Response.txt"
            if os.path.exists(os.path.join(attempt_dir, fname)):
                fname = _reserve_filename(fname, used)
            _write_text_file(attempt_dir + os.sep + fname, raw_name, asgn_name,
                             score, sub_at, body)
            files_ok.append(fname)
            n_written += 1

        url_sub = (sub.get("url") or "").strip()
        if url_sub:
            fname = "Submitted URL.txt"
            if os.path.exists(os.path.join(attempt_dir, fname)):
                fname = _reserve_filename(fname, used)
            with open(os.path.join(attempt_dir, fname), "w", encoding="utf-8") as f:
                f.write(f"Assignment: {asgn_name}\nSubmitted: {sub_at}\n\n{url_sub}\n")
            files_ok.append(fname)
            n_written += 1

        for att in (sub.get("attachments") or []):
            orig = att.get("filename") or att.get("display_name") or "file"
            safe_orig = safe_name(os.path.basename(orig), 150)
            fname = safe_orig
            if os.path.exists(os.path.join(attempt_dir, fname)):
                fname = _reserve_filename(fname, used)
            try:
                _download_binary(session, att["url"], os.path.join(attempt_dir, fname))
                files_ok.append(fname)
                n_written += 1
            except Exception as e:
                yield f"      !! {raw_name} — file download failed: {type(e).__name__}"

        index_rows.append({
            "name": raw_name, "user_id": uid, "attempt": attempt, "score": score,
            "workflow": state, "submitted": sub_at,
            "files": "; ".join(files_ok),
        })

    idx = os.path.join(assignment_dir, "_index.csv")
    with open(idx, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["name", "user_id", "attempt", "score", "workflow", "submitted", "files"])
        w.writeheader()
        w.writerows(index_rows)

    n_total = len(index_rows)
    n_nosub = sum(1 for r in index_rows if not r["files"])
    yield f"      ✓ {n_written} files  |  {n_total} students  |  {n_nosub} no submission"
    yield f"      📁 {assignment_dir}"


def run_download(course_id, course_name, assignment_ids,
                 canvas_base, token, download_root):
    """Generator whose final line is ``COURSE_FOLDER: <absolute path>``."""
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"
    course_dir = _course_dir(download_root, course_name, course_id)
    os.makedirs(course_dir, exist_ok=True)
    yield f"Destination: {course_dir}"
    yield f"Assignments to download: {len(assignment_ids)}"
    yield ""

    for asgn_id in assignment_ids:
        try:
            r = session.get(
                f"{canvas_base}/api/v1/courses/{course_id}/assignments/{asgn_id}",
                timeout=15,
            )
            if r.status_code != 200:
                yield f"  !! assignment {asgn_id}: HTTP {r.status_code}"
                continue
            assignment = r.json()
            course_info = [
                ("Current Canvas name", course_name),
                ("Canvas course ID", course_id),
            ]
            yield from _download_assignment(
                session, canvas_base, course_id, assignment, course_dir,
                course_name=course_name, course_info=course_info,
            )
        except Exception as e:
            yield f"  !! assignment {asgn_id}: {type(e).__name__}"
        yield ""
    yield f"COURSE_FOLDER: {course_dir}"
