"""FastAPI shell for the local DataForge assessment engine."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from api.mirror import store as mirror_store
from api.dataforge import paths as dataforge_paths
from api.dataforge import views

from api.platform_services import config
from ..deps import templates
from ..local_request_guard import csrf_token


router = APIRouter(prefix="/assessments", tags=["assessments"])

_ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}
_TEMPLATES = {
    "index.html": "assessments.html",
    "coverage.html": "assessment_coverage.html",
    "results.html": "assessment_results.html",
    "dashboard.html": "assessment_dashboard.html",
    "history.html": "assessment_history.html",
}
_ENDPOINTS = {
    "index": "assessments_index",
    "process": "assessments_process",
    "dashboard": "assessments_dashboard",
    "history": "assessments_history",
    "history_update": "assessments_history_update",
    "history_delete": "assessments_history_delete",
    "results": "assessments_results",
    "export_standards_profile": "assessments_export_standards_profile",
    "download": "assessments_download",
    "download_all": "assessments_download_all",
}


def _safe_upload_name(filename: str) -> str:
    name = Path(filename or "").name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return name or "upload"


def _attachment_header(filename: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._ -]+", "_", filename).strip(" .") or "download"
    return f'attachment; filename="{safe}"'


def _url_for(request: Request, endpoint: str, **params) -> str:
    route_name = _ENDPOINTS.get(endpoint)
    if route_name is None:
        raise HTTPException(status_code=500, detail="Unknown assessment redirect")
    return str(request.url_for(route_name, **params))


def _course_options() -> list[dict]:
    try:
        courses = config.active_courses()
    except Exception:
        return []
    options = []
    for course in courses if isinstance(courses, list) else []:
        if not isinstance(course, dict) or not str(course.get("id") or "").strip():
            continue
        options.append({
            "id": str(course["id"]),
            "label": str(course.get("nickname") or course.get("name") or course["id"]),
        })
    return options


def _respond(request: Request, result):
    if isinstance(result, views.Render):
        template = _TEMPLATES.get(result.template)
        if template is None:
            raise HTTPException(status_code=500, detail="Unknown assessment template")
        context = dict(result.context)
        context.update({"nav_section": "assessments", "csrf_token": csrf_token()})
        return templates.TemplateResponse(request, template, context)
    if isinstance(result, views.Redirect):
        return RedirectResponse(_url_for(request, result.endpoint, **result.params), status_code=303)
    if isinstance(result, views.FileDownload):
        path = Path(result.path)
        return FileResponse(
            path,
            media_type="application/octet-stream",
            filename=result.download_name or path.name,
        )
    if isinstance(result, views.BytesDownload):
        return Response(
            content=result.data,
            media_type=result.mimetype,
            headers={"Content-Disposition": _attachment_header(result.download_name)},
        )
    raise HTTPException(status_code=500, detail="Unhandled assessment response")


def _respond_safely(request: Request, operation, *args):
    try:
        return _respond(request, operation(*args))
    except views.NotFound as exc:
        raise HTTPException(status_code=404, detail="Assessment artifact not found") from exc


@router.get("", name="assessments_index", response_class=HTMLResponse)
def index(request: Request):
    return _respond_safely(request, views.index)


@router.post("/process", name="assessments_process")
def process(
    request: Request,
    files: list[UploadFile] | None = File(default=None),
    anonymize: bool = Form(default=False),
    use_existing: bool = Form(default=False),
):
    paths = dataforge_paths.get_paths()
    upload_paths = []
    for upload in files or []:
        filename = _safe_upload_name(upload.filename or "")
        if Path(filename).suffix.lower() not in _ALLOWED_EXTENSIONS:
            continue
        destination = paths.upload_dir / filename
        with destination.open("wb") as target:
            shutil.copyfileobj(upload.file, target)
        upload_paths.append(destination)
    return _respond_safely(request, views.process, anonymize, use_existing, upload_paths)


@router.get("/coverage", name="assessments_coverage", response_class=HTMLResponse)
def coverage(request: Request, course_id: str = ""):
    roster_document = mirror_store.read_roster(course_id) if course_id else None

    def build_result():
        result = views.coverage(course_id, roster_document)
        if isinstance(result, views.Render):
            result.context["course_options"] = _course_options()
        return result

    return _respond_safely(request, build_result)


@router.get("/dashboard/{run_id}", name="assessments_dashboard", response_class=HTMLResponse)
def dashboard(request: Request, run_id: str):
    return _respond_safely(request, views.dashboard, run_id)


@router.get("/history", name="assessments_history", response_class=HTMLResponse)
def history(request: Request):
    return _respond_safely(request, views.history)


@router.post("/history/update", name="assessments_history_update")
def history_update(request: Request, snap_id: str = Form(default=""), new_date: str = Form(default="")):
    return _respond_safely(request, views.history_update, snap_id, new_date)


@router.post("/history/delete", name="assessments_history_delete")
def history_delete(request: Request, snap_id: str = Form(default="")):
    return _respond_safely(request, views.history_delete, snap_id)


@router.get("/results/{run_id}", name="assessments_results", response_class=HTMLResponse)
def results(request: Request, run_id: str):
    return _respond_safely(request, views.results, run_id)


@router.get("/export/standards-profile", name="assessments_export_standards_profile")
def export_standards_profile(request: Request):
    return _respond_safely(request, views.export_standards_profile)


@router.get("/download/{name:path}", name="assessments_download")
def download(request: Request, name: str):
    return _respond_safely(request, views.download, name)


@router.get("/download-all/{run_id}", name="assessments_download_all")
def download_all(request: Request, run_id: str):
    return _respond_safely(request, views.download_all, run_id)
