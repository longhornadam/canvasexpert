"""Canvas submission downloader.

Writes student submissions to a structured local folder tree:

  <root>/
    <Course Name>/
      by_assignment/
        <Assignment Title>/
          _index.csv                         -- every student: score, state, files
          <Assignment> - <F Last>.html       -- online_text_entry / discussion body
          <Assignment> - <F Last> - <file>   -- online_upload (original file)
      by_student/
        <Student Name>/
          _portfolio.csv               -- all assignments + scores for this student
          <Assignment> - <F Last>.html
          <Assignment> - <F Last> - <file>

Usage (as a generator — yields progress strings):
    for line in run_download(course_id, course_name, assignment_ids,
                             canvas_base, token, download_root):
        print(line)
    # Final yielded line: "COURSE_FOLDER: /path/to/folder"
"""
import csv
import os
import re
import shutil

import requests


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def safe_name(s: str, max_len: int = 80) -> str:
    """Return a filesystem-safe string (Windows + POSIX compatible)."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(s))
    s = s.strip('. ')
    return s[:max_len] or '_unnamed'


def _name_parts(raw_name):
    """Best-effort first/last extraction from Canvas display or sortable names."""
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


def _student_file_tag(user, fallback_user_id=None):
    """Return the requested first-initial + last-name suffix for filenames."""
    user = user or {}
    for key in ("sortable_name", "name"):
        first, last = _name_parts(user.get(key))
        if first and last:
            return safe_name(f"{first[:1].upper()} {last}", 40)
    fallback = (user.get("name") or user.get("sortable_name")
                or f"user_{fallback_user_id}")
    return safe_name(fallback, 40)


def _assignment_student_stem(assignment_name, student_tag, max_len=110):
    """Build '<assignment> - <F Last>' while preserving the student suffix."""
    tag = safe_name(student_tag, 40)
    sep = " - "
    max_assignment = max(1, max_len - len(sep) - len(tag))
    assignment_part = safe_name(assignment_name, max_assignment)
    return f"{assignment_part}{sep}{tag}"


def _work_filename(assignment_name, student_tag, ext="", detail=""):
    """Filename for one downloaded work item."""
    stem = _assignment_student_stem(assignment_name, student_tag)
    if detail:
        stem += " - " + safe_name(detail, 40)
    return stem + (ext or "")


def _reserve_filename(filename, used):
    """Keep names stable on rerun while preventing collisions in this batch."""
    stem, ext = os.path.splitext(filename)
    candidate = filename
    n = 2
    while candidate in used:
        candidate = f"{stem} ({n}){ext}"
        n += 1
    used.add(candidate)
    return candidate


def _get_all_pages(session, url, params=None):
    """Fetch every page of a Canvas paginated endpoint; returns combined list."""
    results, params = [], dict(params or {})
    params.setdefault("per_page", 100)
    while url:
        r = session.get(url, params=params, timeout=30)
        r.raise_for_status()
        results.extend(r.json())
        params = {}          # subsequent pages: URL already has query string
        url = None
        for part in r.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break
    return results


def _write_text_file(path, student, assignment, score, submitted_at, body):
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            f"<!--\n  Student:    {student}\n"
            f"  Assignment: {assignment}\n"
            f"  Score:      {score}\n"
            f"  Submitted:  {submitted_at}\n-->\n\n"
        )
        f.write(body)


def _download_binary(session, url, dest):
    r = session.get(url, stream=True, allow_redirects=True, timeout=120)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=16_384):
            f.write(chunk)


def _mirror(by_stu_dir, student_name, filename, src_path):
    """Hard-link or copy a file into by_student/<name>/."""
    stu_dir = os.path.join(by_stu_dir, safe_name(student_name))
    os.makedirs(stu_dir, exist_ok=True)
    shutil.copy2(src_path, os.path.join(stu_dir, filename))


def _append_portfolio(stu_dir, student_name, assignment_name, score, state, files):
    os.makedirs(stu_dir, exist_ok=True)
    port = os.path.join(stu_dir, "_portfolio.csv")
    new  = not os.path.exists(port)
    with open(port, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["assignment", "score", "workflow", "files"])
        if new:
            w.writeheader()
        w.writerow({"assignment": assignment_name, "score": score,
                    "workflow": state, "files": files})


# --------------------------------------------------------------------------
# Per-assignment download
# --------------------------------------------------------------------------

DOWNLOADABLE_TYPES = {"online_text_entry", "online_upload", "discussion_topic", "online_url"}


def _download_assignment(session, canvas_base, course_id, assignment, course_dir):
    """Yields progress lines, downloads all submissions for one assignment."""
    asgn_id   = assignment["id"]
    asgn_name = assignment.get("name", f"assignment_{asgn_id}")
    sub_types = set(assignment.get("submission_types") or [])
    points    = assignment.get("points_possible", "?")

    yield f"  ▶ {asgn_name}  ({', '.join(sub_types) or 'none'})  [{points} pts]"

    if not (sub_types & DOWNLOADABLE_TYPES):
        yield f"      – skipped (type not downloadable)"
        return

    by_asgn = os.path.join(course_dir, "by_assignment", safe_name(asgn_name))
    by_stu  = os.path.join(course_dir, "by_student")
    os.makedirs(by_asgn, exist_ok=True)

    # Pull all submissions with user info
    subs = _get_all_pages(
        session,
        f"{canvas_base}/api/v1/courses/{course_id}/assignments/{asgn_id}/submissions",
        {"include[]": "user"},
    )

    index_rows = []
    n_written  = 0
    used_filenames = set()

    for sub in subs:
        user     = sub.get("user") or {}
        name     = (user.get("name") or user.get("sortable_name")
                    or f"user_{sub['user_id']}")
        file_tag = _student_file_tag(user, sub.get("user_id"))
        score    = sub.get("score", "")
        state    = sub.get("workflow_state", "")
        sub_at   = (sub.get("submitted_at") or "")[:19].replace("T", " ")
        files_ok = []

        # ── inline text ─────────────────────────────────────────────────
        body = (sub.get("body") or "").strip()
        if body:
            fname       = _reserve_filename(
                _work_filename(asgn_name, file_tag, ".html"),
                used_filenames,
            )
            mirror_name = fname
            dest  = os.path.join(by_asgn, fname)
            _write_text_file(dest, name, asgn_name, score, sub_at, body)
            _mirror(by_stu, name, mirror_name, dest)
            files_ok.append(fname)
            n_written += 1

        # ── URL submission ───────────────────────────────────────────────
        url_sub = (sub.get("url") or "").strip()
        if url_sub:
            fname       = _reserve_filename(
                _work_filename(asgn_name, file_tag, ".txt", "URL"),
                used_filenames,
            )
            mirror_name = fname
            dest  = os.path.join(by_asgn, fname)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(f"Student:    {name}\n")
                f.write(f"Assignment: {asgn_name}\n")
                f.write(f"Score:      {score}\n")
                f.write(f"Submitted:  {sub_at}\n\n")
                f.write(url_sub + "\n")
            _mirror(by_stu, name, mirror_name, dest)
            files_ok.append(fname)
            n_written += 1

        # ── file attachments ─────────────────────────────────────────────
        for att in (sub.get("attachments") or []):
            orig  = att.get("filename") or att.get("display_name") or "file"
            detail, ext_orig = os.path.splitext(orig)
            fname = _reserve_filename(
                _work_filename(asgn_name, file_tag, ext_orig, detail or "file"),
                used_filenames,
            )
            mirror_name = fname
            dest = os.path.join(by_asgn, fname)
            try:
                _download_binary(session, att["url"], dest)
                _mirror(by_stu, name, mirror_name, dest)
                files_ok.append(fname)
                n_written += 1
            except Exception as e:
                yield f"      !! {name} — file download failed: {e}"

        # ── portfolio row ────────────────────────────────────────────────
        stu_dir = os.path.join(by_stu, safe_name(name))
        _append_portfolio(stu_dir, name, asgn_name, score, state,
                          "; ".join(files_ok))

        index_rows.append({
            "name": name, "user_id": sub["user_id"],
            "score": score, "workflow": state,
            "submitted": sub_at, "files": "; ".join(files_ok),
        })

    # _index.csv
    idx = os.path.join(by_asgn, "_index.csv")
    with open(idx, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["name","user_id","score","workflow","submitted","files"])
        w.writeheader()
        w.writerows(index_rows)

    n_total = len(index_rows)
    n_nosub = sum(1 for r in index_rows if not r["files"])
    yield f"      ✓ {n_written} files  |  {n_total} students  |  {n_nosub} no submission"
    yield f"      📁 {by_asgn}"


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------

def run_download(course_id, course_name, assignment_ids,
                 canvas_base, token, download_root):
    """Generator: yields progress strings.
    Final line is always  COURSE_FOLDER: <absolute path>
    """
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    course_dir = os.path.join(download_root, safe_name(course_name))
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
            yield from _download_assignment(session, canvas_base, course_id,
                                             r.json(), course_dir)
        except Exception as e:
            yield f"  !! assignment {asgn_id}: {e}"
        yield ""

    yield f"COURSE_FOLDER: {course_dir}"
