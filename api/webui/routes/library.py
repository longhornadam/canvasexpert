"""Library and AI-TA file routes for Canvas Expert.

One APIRouter; 7 routes for file listing, AI-TA management, validation, and downloads.

Routes: GET  /api/files
        GET  /api/rf/files
        GET  /api/ai-ta/files
        GET  /api/ai-ta/file
        GET  /api/ai-ta/toolkit-file
        POST /api/ai-ta/rebuild
        GET  /api/download-contract
"""
import os

from fastapi import APIRouter, Form, Request, UploadFile, File
from fastapi.responses import JSONResponse, PlainTextResponse, FileResponse

from .. import ai_ta
from api import runtime_paths
from ..deps import REPO_ROOT, list_ai_ta_files, list_quiz_files, list_rubric_files

router = APIRouter(tags=["library"])


@router.get("/api/files")
def api_files():
    return JSONResponse({"files": list_quiz_files()})


@router.get("/api/rf/files")
def api_rf_files():
    return JSONResponse({"files": list_rubric_files()})


@router.get("/api/ai-ta/files")
def api_ai_ta_files():
    return JSONResponse({"files": list_ai_ta_files()})


@router.get("/api/ai-ta/file")
def api_ai_ta_file(name: str):
    """Return the content of one AI-TA flat file by basename.
    Validates the name is within the current AI-TA directory to prevent path traversal."""
    if not name or os.sep in name or "/" in name or ".." in name:
        return JSONResponse({"error": "invalid name"}, status_code=400)
    ai_ta_dir = runtime_paths.ai_ta_dir()
    path = os.path.join(ai_ta_dir, name)
    if not os.path.isfile(path) or not os.path.abspath(path).startswith(
            os.path.abspath(ai_ta_dir)):
        return JSONResponse({"error": "file not found"}, status_code=404)
    with open(path, encoding="utf-8") as f:
        return PlainTextResponse(f.read())


@router.get("/api/ai-ta/toolkit-file")
def api_ai_ta_toolkit_file(name: str):
    """Return content of one MagicSchool Toolkit file by basename."""
    if not name or os.sep in name or "/" in name or ".." in name:
        return JSONResponse({"error": "invalid name"}, status_code=400)
    toolkit_dir = os.path.join(runtime_paths.ai_ta_dir(), "MagicSchool Toolkit")
    path = os.path.join(toolkit_dir, name)
    if not os.path.isfile(path) or not os.path.abspath(path).startswith(
            os.path.abspath(toolkit_dir)):
        return JSONResponse({"error": "file not found"}, status_code=404)
    with open(path, encoding="utf-8") as f:
        return PlainTextResponse(f.read())


@router.post("/api/ai-ta/rebuild")
def api_ai_ta_rebuild():
    try:
        files = ai_ta.build_library(runtime_paths.ai_ta_dir(), rubric_folders=None)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})
    return JSONResponse({"ok": True, "files": [os.path.basename(p) for p in files]})


@router.get("/api/download-contract")
def api_download_contract(name: str):
    """Download a Forge contract file (e.g. AssignmentForge_Base, PageForge_Base)."""
    valid_names = {"AssignmentForge_Base", "PageForge_Base", "QuizForge_Base",
                   "RubricForge_Base"}
    if name not in valid_names:
        return JSONResponse({"error": "unknown contract"}, status_code=400)
    path = os.path.join(REPO_ROOT, "LLM_Modules", f"{name}.md")
    if not os.path.isfile(path):
        return JSONResponse({"error": "file not found"}, status_code=404)
    return FileResponse(path, media_type="text/markdown",
                        filename=f"{name}.md")
