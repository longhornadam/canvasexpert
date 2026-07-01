"""Push and validation routes for Canvas Expert.

One APIRouter; 14 routes for file validation, content push, and streaming push output.

Routes: POST /api/temp-upload
        POST /api/validate
        POST /api/physical/quiz
        POST /api/nf/validate
        POST /api/physical/note
        POST /api/af/validate
        POST /api/pf/validate
        POST /api/rf/validate
        GET  /api/rf/scoring-prompt
        GET  /api/modules
        GET  /api/assignment-groups
        POST /api/push/preview
        GET  /api/push/stream
        GET  /api/push-multi-whole/stream
        GET  /api/push-variants/stream
        GET  /api/push-multi/stream
        POST /api/content/push
"""
import json
import os
import sys
import tempfile
import uuid as _uuid

from fastapi import APIRouter, Form, File, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, FileResponse, StreamingResponse

from .. import af, pf, rf, config, runner
from ..canvas_client import _canvas_get, _canvas_get_all, _canvas_send
from ..deps import TEMP_DIR, _exports_dir, _workspace_folder, REPO_ROOT, API_DIR, _sse
from ..gradebook_service import _expand_variants_extra_time
from ..push_service import (
    _find_assignment_group, _find_or_create_module_id, _add_module_item,
    _push_assignment, _push_page, _push_quick, _CONTENT_PUSHERS,
)

router = APIRouter(tags=["push"])


# --------------------------------------------------------------------------
# Route handlers
# --------------------------------------------------------------------------

@router.post("/api/temp-upload")
async def api_temp_upload(
    content: str = Form(default=""),
    file: UploadFile = File(default=None),
):
    """Save pasted JSON text or an uploaded file to a temp location; return the path."""
    fname = f"temp_{_uuid.uuid4().hex}.json"
    path = os.path.join(TEMP_DIR, fname)
    if file and file.filename:
        data = await file.read()
        with open(path, "wb") as fh:
            fh.write(data)
    elif content.strip():
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
    else:
        return JSONResponse({"ok": False, "error": "No content or file provided"})
    return JSONResponse({"ok": True, "path": path})


@router.post("/api/validate")
def api_validate(path: str = Form(...)):
    import validate_qf
    seen = set()
    try:
        problems = validate_qf.validate(path, seen)
    except FileNotFoundError:
        return JSONResponse({"ok": False, "error": f"file not found: {path}"})
    return JSONResponse({"ok": not problems, "problems": problems})


@router.post("/api/physical/quiz")
def api_physical_quiz(path: str = Form(...)):
    """Compile printable PDF + DOCX files from a <QUIZFORGE_JSON> file."""
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    try:
        from engine.importers import import_quiz_from_llm
        from engine.validation.point_calculator import calculate_points
        from engine.validation.answer_balancer import balance_answers
        from engine.rendering.physical.styles.default_styles import DEFAULT_QUIZ_POINTS
        from engine.packagers.physical_handler import generate_physical_outputs
        from engine.packaging.folder_creator import create_quiz_folder
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"engine unavailable: {e}"})

    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as e:
        return JSONResponse({"ok": False, "error": f"cannot read file: {e}"})

    try:
        from pathlib import Path as _Path
        quiz = import_quiz_from_llm(text).quiz
        try:
            quiz.questions = calculate_points(quiz.questions, total_points=DEFAULT_QUIZ_POINTS)
            quiz.questions = balance_answers(quiz.questions)
        except Exception:
            pass
        base = _exports_dir()
        os.makedirs(base, exist_ok=True)
        folder = create_quiz_folder(_Path(base), quiz.title)
        results = generate_physical_outputs(quiz, str(folder))
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})

    log_path = results.get("log_path")
    warnings = []
    if log_path:
        try:
            with open(log_path, encoding="utf-8") as fh:
                warnings = [
                    line.strip()
                    for line in fh
                    if line.startswith("PHYSICAL RENDER WARNING")
                ]
            os.remove(log_path)
        except OSError:
            pass

    files = [os.path.basename(results[k])
             for k in ("quiz_path", "quiz_pdf_path", "key_path", "key_pdf_path", "rationale_path")
             if results.get(k)]
    fallback = not bool(_workspace_folder("Exports"))
    return JSONResponse({"ok": True, "folder": str(folder),
                         "files": files, "warnings": warnings,
                         "warning": warnings[0] if warnings else "",
                         "fallback": fallback})


@router.post("/api/nf/validate")
def api_nf_validate(path: str = Form(...)):
    """Validate enough NoteForge shape to summarize what the physical renderer will use."""
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    try:
        from engine.rendering.physical.note_adapter import load_noteforge_json, to_printdoc
        from engine.rendering.physical.redact import iter_slots
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"engine unavailable: {e}"})

    try:
        note = load_noteforge_json(path)
        printdoc = to_printdoc(note)
    except Exception as e:
        return JSONResponse({"ok": False, "problems": [str(e)], "summary": None})

    problems = []
    if note.get("version") != "1.0-json":
        problems.append(f"version must be \"1.0-json\" (got {note.get('version')!r})")
    if note.get("type") not in {"guided_notes", "cornell", "frayer"}:
        problems.append(f"unknown NoteForge type: {note.get('type')!r}")

    summary = {
        "type": note.get("type"),
        "title": printdoc.title,
        "mode": note.get("mode") or "blank",
        "slot_count": len(list(iter_slots(printdoc))),
    }
    return JSONResponse({"ok": not problems, "problems": problems, "summary": summary})


def _note_files_from_results(results: dict) -> list[str]:
    files = []
    for artifact in (results.get("artifacts") or {}).values():
        for key in ("docx_path", "pdf_path"):
            path = artifact.get(key)
            if path:
                files.append(os.path.basename(path))
    return files


def _primary_note_pdf(results: dict) -> str:
    artifacts = results.get("artifacts") or {}
    for label in ("Core", "Exemplar", "Support", "Accelerate", "Extend"):
        pdf = (artifacts.get(label) or {}).get("pdf_path")
        if pdf:
            return pdf
    for label, artifact in artifacts.items():
        if label == "KEY":
            continue
        pdf = artifact.get("pdf_path")
        if pdf:
            return pdf
    return ""


@router.post("/api/physical/note")
def api_physical_note(path: str = Form(...)):
    """Compile tiered printable PDF + DOCX files from a <NOTEFORGE_JSON> file."""
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    try:
        from pathlib import Path as _Path
        from engine.packagers.note_handler import generate_note_outputs
        from engine.packaging.folder_creator import create_quiz_folder
        from engine.rendering.physical.note_adapter import load_noteforge_json, to_printdoc
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"engine unavailable: {e}"})

    try:
        note = load_noteforge_json(path)
        title = to_printdoc(note).title
        base = _exports_dir()
        os.makedirs(base, exist_ok=True)
        folder = create_quiz_folder(_Path(base), title)
        results = generate_note_outputs(note, str(folder))
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})

    log_path = results.get("log_path")
    warnings = []
    if log_path:
        try:
            with open(log_path, encoding="utf-8") as fh:
                warnings = [
                    line.strip()
                    for line in fh
                    if line.startswith("PHYSICAL RENDER WARNING")
                ]
            os.remove(log_path)
        except OSError:
            pass

    fallback = not bool(_workspace_folder("Exports"))
    return JSONResponse({
        "ok": True,
        "folder": str(folder),
        "title": title,
        "files": _note_files_from_results(results),
        "artifacts": results.get("artifacts") or {},
        "primary_pdf": _primary_note_pdf(results),
        "warnings": warnings,
        "warning": warnings[0] if warnings else "",
        "fallback": fallback,
    })


@router.post("/api/af/validate")
def api_af_validate(path: str = Form(...)):
    """Validate an <ASSIGNMENTFORGE_JSON> file and summarize what it would push."""
    data, problems = af.parse_file(path)
    summary = None
    if data is not None:
        tiers = data.get("tiers") or []
        summary = {
            "type":   data.get("type"),
            "title":  data.get("title"),
            "points": data.get("points", 100),
            "submission_types": (data.get("submission") or {}).get(
                "types", ["online_text_entry"]),
            "tiers": [{"label": t.get("label"), "group": t.get("group"),
                       "scaffolded": bool(t.get("scaffolding") or t.get("description"))}
                      for t in tiers],
            "placeholders": sorted(set(
                f"{k}:{v.strip()}" for k, v in
                af.PLACEHOLDER_RE.findall(str(data.get("description", "")) + "".join(
                    str(t.get("description") or "") + str(t.get("scaffolding") or "")
                    for t in tiers)))),
        }
    return JSONResponse({"ok": data is not None and not problems,
                         "problems": problems, "summary": summary})


@router.post("/api/pf/validate")
def api_pf_validate(path: str = Form(...)):
    """Validate a <PAGEFORGE_JSON> file and summarize what it would push."""
    data, problems = pf.parse_file(path)
    summary = None
    if data is not None:
        summary = {
            "type":  data.get("type"),
            "title": data.get("title"),
            "placeholders": sorted(set(
                f"{k}:{v.strip()}" for k, v in
                pf.PLACEHOLDER_RE.findall(str(data.get("body", ""))))),
        }
    return JSONResponse({"ok": data is not None and not problems,
                         "problems": problems, "summary": summary})


@router.post("/api/rf/validate")
def api_rf_validate(path: str = Form(...)):
    """Validate a <RUBRICFORGE_JSON> file and summarize what it would push."""
    data, problems = rf.parse_file(path)
    summary = None
    if data is not None:
        summary = rf.summary(data)
    return JSONResponse({"ok": data is not None and not problems,
                         "problems": problems, "summary": summary})


@router.get("/api/rf/scoring-prompt")
def api_rf_scoring_prompt(path: str):
    data, problems = rf.parse_file(path)
    if data is None or problems:
        return JSONResponse({"ok": False, "problems": problems or ["unreadable file"]}, status_code=400)
    return PlainTextResponse(rf.scoring_prompt(data))


@router.get("/api/modules")
def get_modules(course_id: str):
    """Canvas Modules list for a course."""
    data, err = _canvas_get(f"/api/v1/courses/{course_id}/modules", {"per_page": 100})
    if err:
        return JSONResponse({"ok": False, "error": err})
    modules = [{"id": str(m["id"]), "name": m["name"]}
               for m in (data or []) if "id" in m]
    return JSONResponse({"ok": True, "modules": modules})


@router.get("/api/assignment-groups")
def get_assignment_groups(course_id: str):
    """Grading categories (Canvas assignment groups) for a course."""
    data, err = _canvas_get(f"/api/v1/courses/{course_id}/assignment_groups")
    if err:
        return JSONResponse({"ok": False, "error": err})
    groups = [{"id": str(g["id"]), "name": g["name"]}
              for g in (data or []) if "id" in g]
    return JSONResponse({"ok": True, "groups": groups})


@router.post("/api/push/preview")
def api_push_preview(course_id: str = Form(...), path: str = Form(...), settings: str = Form("")):
    try:
        env = config.resolve_env(course_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)})
    if settings:
        env["QF_PUSH_SETTINGS"] = settings
    code, output = runner.run_capture(["qf_pusher.py", path, "--dry-run"], env)
    return JSONResponse({"ok": code == 0, "output": output})


@router.get("/api/push/stream")
def api_push_stream(course_id: str, path: str, settings: str = ""):
    try:
        env = config.resolve_env(course_id)
    except ValueError as e:
        return StreamingResponse(_sse([f"!! {e}", "[exit 1]"]), media_type="text/event-stream")
    if settings:
        env["QF_PUSH_SETTINGS"] = settings
    return StreamingResponse(
        _sse(runner.run_streaming(["qf_pusher.py", path], env)),
        media_type="text/event-stream")


@router.post("/api/content/push")
def api_content_push(kind: str = Form(...), courses: str = Form(...), payload: str = Form(...)):
    """Create an assignment / page in every target course."""
    fn = _CONTENT_PUSHERS.get(kind)
    if not fn:
        return JSONResponse({"ok": False, "error": f"unknown kind '{kind}'"})
    try:
        targets = json.loads(courses)
        p = json.loads(payload)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})
    if not targets:
        return JSONResponse({"ok": False, "error": "no courses selected"})

    results = []
    for t in targets:
        cid = str(t.get("id", ""))
        cname = t.get("name", f"course {cid}")
        notes = []
        result = fn(cid, p, notes)
        if hasattr(result, "ok"):
            ok = result.ok
            title = result.title
            url = result.url
            error = result.error
            assignment_id = getattr(result, "assignment_id", None)
        else:
            ok, title, url, error = result
            assignment_id = None
        results.append({"course_id": cid, "course_name": cname, "ok": ok,
                        "title": title, "url": url, "assignment_id": assignment_id,
                        "error": error, "notes": notes})
    return JSONResponse({"ok": all(r["ok"] for r in results), "results": results})


# --------------------------------------------------------------------------
# Multi-course push streaming endpoints
# --------------------------------------------------------------------------

@router.get("/api/push-multi-whole/stream")
def api_push_multi_whole_stream(course_ids: str, path: str, settings: str = ""):
    """Push the SAME whole-class quiz to several courses in one operation."""
    import re as _re
    ids = [c.strip() for c in course_ids.split(",") if c.strip()]
    if not ids:
        return StreamingResponse(_sse(["!! no courses selected", "[exit 1]"]),
                                 media_type="text/event-stream")

    def lines():
        all_ok = True
        for idx, cid in enumerate(ids):
            yield ""
            yield f"{'─'*60}"
            yield f"  Course {idx+1}/{len(ids)}:  #{cid}"
            yield f"{'─'*60}"
            try:
                env = config.resolve_env(cid)
            except ValueError as e:
                yield f"  !! {e}"; all_ok = False; continue
            if settings:
                env["QF_PUSH_SETTINGS"] = settings
            for line in runner.run_streaming(["qf_pusher.py", path], env):
                if _re.match(r"^\[exit \d+\]$", line):
                    if line != "[exit 0]":
                        all_ok = False
                else:
                    yield line
        yield "[exit 0]" if all_ok else "[exit 1]"

    return StreamingResponse(_sse(lines()), media_type="text/event-stream")


@router.get("/api/push-variants/stream")
def api_push_variants_stream(course_id: str, manifest: str, settings: str = ""):
    """Push differentiated variants to a single course."""
    try:
        env = config.resolve_env(course_id)
    except ValueError as e:
        return StreamingResponse(_sse([f"!! {e}", "[exit 1]"]),
                                 media_type="text/event-stream")
    if settings:
        env["QF_PUSH_SETTINGS"] = settings
    try:
        entries = json.loads(manifest)
    except json.JSONDecodeError as e:
        return StreamingResponse(_sse([f"!! bad manifest: {e}", "[exit 1]"]),
                                 media_type="text/event-stream")

    entries = _expand_variants_extra_time(course_id, entries, settings)

    fd, tmp = tempfile.mkstemp(prefix="qf_variants_", suffix=".json", dir=API_DIR)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(entries, f)

    def lines():
        try:
            yield from runner.run_streaming(["push_tiers.py", "--manifest", tmp], env)
        finally:
            try: os.remove(tmp)
            except OSError: pass

    return StreamingResponse(_sse(lines()), media_type="text/event-stream")


@router.get("/api/push-multi/stream")
def api_push_multi_stream(multi_manifest: str, settings: str = ""):
    """Push differentiated variants to multiple courses in one operation."""
    import re as _re
    try:
        courses = json.loads(multi_manifest)
    except json.JSONDecodeError as e:
        return StreamingResponse(_sse([f"!! bad manifest: {e}", "[exit 1]"]),
                                 media_type="text/event-stream")

    def lines():
        all_ok = True
        for idx, course in enumerate(courses):
            cid  = str(course["course_id"])
            name = course.get("course_name", f"course {cid}")
            variants = course["variants"]
            yield ""
            yield f"{'─'*60}"
            yield f"  Course {idx+1}/{len(courses)}: {name}  (#{cid})"
            yield f"{'─'*60}"
            try:
                env = config.resolve_env(cid)
            except ValueError as e:
                yield f"  !! {e}"; all_ok = False; continue
            if settings:
                env["QF_PUSH_SETTINGS"] = settings

            variants = _expand_variants_extra_time(cid, variants, settings)

            fd, tmp = tempfile.mkstemp(prefix="qf_multi_", suffix=".json", dir=API_DIR)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(variants, f)
            try:
                for line in runner.run_streaming(
                        ["push_tiers.py", "--manifest", tmp], env):
                    if _re.match(r"^\[exit \d+\]$", line):
                        if line != "[exit 0]":
                            all_ok = False
                    else:
                        yield line
            finally:
                try: os.remove(tmp)
                except OSError: pass

        yield "[exit 0]" if all_ok else "[exit 1]"

    return StreamingResponse(_sse(lines()), media_type="text/event-stream")
