"""Validation and physical-render routes used by the push UI."""
import os
import sys
import uuid as _uuid

from fastapi import File, Form, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse

from .. import af, pf, rf
from ..deps import TEMP_DIR, REPO_ROOT, _exports_dir, _workspace_folder


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


def register_validation_routes(router, exports_dir_func=_exports_dir, workspace_folder_func=_workspace_folder):
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
            base = exports_dir_func()
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

        files = [
            os.path.basename(results[k])
            for k in ("quiz_path", "quiz_pdf_path", "key_path", "key_pdf_path", "rationale_path")
            if results.get(k)
        ]
        fallback = not bool(workspace_folder_func("Exports"))
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
            base = exports_dir_func()
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

        fallback = not bool(workspace_folder_func("Exports"))
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
                "type": data.get("type"),
                "title": data.get("title"),
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
                "type": data.get("type"),
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
