"""Streaming push routes for QuizForge whole-class and differentiated pushes."""
import json
import os
import tempfile

from fastapi import Form
from fastapi.responses import JSONResponse, StreamingResponse

from .. import config, runner
from ..deps import API_DIR, _sse
from ..gradebook_service import _expand_variants_extra_time


def register_streaming_routes(router):
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
                cid = str(course["course_id"])
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
