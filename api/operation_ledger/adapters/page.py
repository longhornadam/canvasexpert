"""PageForge page adapter — the slice-10 pilot kind ``content.page``.

Implements the full OperationAdapter protocol:
  build_payload → source_digest → verify_targets → freeze_review →
  capture_baseline → check_drift → execute (create_page + attach_module) →
  reconcile → retry_selector → reversal_descriptor.

Canvas calls reuse the existing ``canvas_client`` wrappers. The adapter never
trusts browser-supplied Canvas paths, endpoints, or method names.
"""
import copy
import hashlib
import json

from .. import models
from api.webui import canvas_client, config, pf


KIND = "content.page"


class PageAdapter:
    """Adapter for PageForge page creation (kind ``content.page``)."""

    kind = KIND

    # ── Prepare ──────────────────────────────────────────────────────────

    def build_payload(self, prepare_request: dict) -> dict:
        """Parse/validate the browser-submitted prepare request.

        Input: ``{path, published, module_name?}``.
        Returns the normalized private payload. Raises ValueError on invalid input.
        Never trusts browser-supplied Canvas paths, endpoints, or method names.
        """
        path = prepare_request.get("path")
        if not path:
            raise ValueError("path is required")

        data, problems = pf.parse_file(path)
        if data is None or problems:
            raise ValueError("; ".join(problems or ["unreadable file"]))

        title = str(data.get("title") or "").strip()
        body = str(data.get("body") or "")
        published = bool(prepare_request.get("published"))
        module_name = prepare_request.get("module_name") or None
        if module_name:
            module_name = str(module_name).strip() or None

        return {
            "title": title,
            "body": body,
            "published": published,
            "module_name": module_name,
            "source_path": path,
        }

    def source_digest(self, payload: dict) -> str:
        """Deterministic SHA-256 over the normalized payload (not including targets)."""
        digest_input = {
            "title": payload.get("title"),
            "body": payload.get("body"),
            "published": payload.get("published"),
            "module_name": payload.get("module_name"),
        }
        return models.sha256_dict(digest_input)

    def verify_targets(self, payload: dict, targets: list[dict]) -> list[dict]:
        """Verify each target against active/available courses.

        Returns the verified target list with target_key and idempotency_key set.
        Raises ValueError if any target is invalid.
        """
        active = config.active_courses()
        active_ids = {str(c["id"]) for c in active}

        verified = []
        for t in targets:
            cid = str(t.get("course_id") or "")
            if not cid:
                raise ValueError("target missing course_id")
            if cid not in active_ids:
                raise ValueError(f"course {cid} is not in active courses")
            verified.append({
                "course_id": cid,
                "target_key": self.target_key(payload, cid),
                "idempotency_key": self.idempotency_key(payload, cid),
            })
        return verified

    def target_key(self, payload: dict, course_id: str) -> str:
        """Deterministic target key for a course."""
        digest = self.source_digest(payload)
        return models.sha256_hex(f"{KIND}|{digest}|{course_id}")

    def idempotency_key(self, payload: dict, course_id: str) -> str:
        """Deterministic idempotency key."""
        digest = self.source_digest(payload)
        normalized_title = _normalize_title(payload.get("title", ""))
        return models.sha256_hex(f"{digest}|{course_id}|{normalized_title}")

    # ── Review ───────────────────────────────────────────────────────────

    def capture_baseline(self, payload: dict, target: dict) -> dict:
        """Read current Canvas/local state for drift detection.

        Called at review time and again at apply time.
        """
        cid = target["course_id"]
        title = payload.get("title", "")
        baseline = {"existing_page": None}

        # Search for a page with the same title (for baseline display only)
        pages, err = canvas_client._canvas_get(
            f"/api/v1/courses/{cid}/pages",
            params={"per_page": 100, "search_term": title},
        )
        if err:
            baseline["canvas_error"] = err
            return baseline

        for page in (_as_list(pages)):
            if str(page.get("title", "")).strip().lower() == title.strip().lower():
                baseline["existing_page"] = {
                    "url": page.get("url"),
                    "title": page.get("title"),
                    "body": page.get("body"),
                    "published": page.get("published"),
                }
                break

        return baseline

    def freeze_review(self, payload: dict, target: dict, baseline: dict) -> dict:
        """Capture the frozen review summary for a target."""
        cid = target["course_id"]
        # Look up course name from active courses (PRIVATE)
        course_name = cid
        for c in config.active_courses():
            if str(c["id"]) == str(cid):
                course_name = c.get("name") or c.get("nickname") or cid
                break

        existing = baseline.get("existing_page")
        return {
            "course_name": course_name,
            "page_title": payload.get("title"),
            "published": payload.get("published"),
            "module_name": payload.get("module_name"),
            "baseline_has_existing_page": existing is not None,
            "baseline_page_url": existing.get("url") if existing else None,
        }

    def check_drift(self, payload: dict, target: dict, baseline: dict) -> bool:
        """Return True if Canvas/local state has drifted since review.

        Drift is detected if:
        - The baseline page was deleted or its body/published state changed.
        - A foreign page with the same title appeared that wasn't in the baseline.
        - Canvas state can't be read.
        """
        if baseline is None:
            return False  # no baseline captured — can't detect drift

        if "canvas_error" in baseline:
            return True  # couldn't read Canvas state → treat as drift

        existing = baseline.get("existing_page")
        cid = target["course_id"]
        title = payload.get("title", "")

        # Re-check the current Canvas state
        pages, err = canvas_client._canvas_get(
            f"/api/v1/courses/{cid}/pages",
            params={"per_page": 100, "search_term": title},
        )
        if err:
            return True  # can't verify → drift

        current = None
        for page in _as_list(pages):
            if str(page.get("title", "")).strip().lower() == title.strip().lower():
                current = page
                break

        if existing is None:
            # No baseline page — drift if a foreign page with the same title appeared
            return current is not None

        if current is None:
            return True  # baseline page was deleted

        # Check body and published state
        if current.get("body") != existing.get("body"):
            return True
        if bool(current.get("published")) != bool(existing.get("published")):
            return True

        return False

    # ── Execute ──────────────────────────────────────────────────────────

    def execute(self, payload: dict, target: dict, baseline: dict, claim: dict) -> dict:
        """Perform the Canvas call(s) for one target.

        Two steps: create_page → attach_module (if module_name is set).
        Returns ``{state, returned_object_id, returned_object_url, error_code,
        private_diagnostic, steps}``.
        """
        cid = target["course_id"]
        title = payload.get("title", "Untitled page")
        body = payload.get("body", "")
        published = bool(payload.get("published"))
        module_name = payload.get("module_name")

        steps = []
        page_slug = target.get("returned_object_id")

        # ── Step 1: create_page ──────────────────────────────────────────
        step1 = models.new_step("create_page")

        # Idempotency: if we have a returned_object_id from a previous attempt,
        # check if the page still exists.
        if page_slug:
            existing_page, err = canvas_client._canvas_get(
                f"/api/v1/courses/{cid}/pages/{page_slug}")
            if not err and existing_page:
                step1["state"] = "skipped"
                step1["returned_object_id"] = page_slug
                step1["updated_at"] = models.now_iso()
                steps.append(step1)
            else:
                # Page not found — need to create
                page_slug = None

        if step1["state"] == "pending":
            wp = {"title": title, "body": body, "published": published}
            resp, err = canvas_client._canvas_send(
                "POST", f"/api/v1/courses/{cid}/pages", {"wiki_page": wp})

            if err:
                if _is_uncertain(err):
                    step1["state"] = "sent_unknown"
                    step1["error_code"] = "timeout_or_disconnect"
                    step1["private_diagnostic"] = err
                else:
                    step1["state"] = "failed"
                    step1["error_code"] = "canvas_rejected"
                    step1["private_diagnostic"] = err
                step1["updated_at"] = models.now_iso()
                steps.append(step1)
                return _build_result(step1["state"], steps=steps,
                                    private_diagnostic=step1.get("private_diagnostic"),
                                    error_code=step1.get("error_code"))
            else:
                page_slug = resp.get("url")
                page_url = resp.get("html_url")
                step1["state"] = "applied"
                step1["returned_object_id"] = page_slug
                step1["updated_at"] = models.now_iso()
                steps.append(step1)

        # ── Step 2: attach_module (only if module_name is set) ────────────
        if module_name and step1["state"] in ("applied", "skipped"):
            step2 = models.new_step("attach_module")
            mid = _find_or_create_module_id(cid, module_name)
            if mid is None:
                step2["state"] = "failed"
                step2["error_code"] = "module_not_found"
                step2["updated_at"] = models.now_iso()
                steps.append(step2)
                # Page was created but module attachment failed → partial
                return _build_result("sent_unknown", steps=steps,
                                    returned_object_id=page_slug,
                                    returned_object_url=page_url if step1["state"] == "applied" else None,
                                    error_code="module_attach_failed")

            item = {"title": title, "type": "Page", "page_url": page_slug}
            _, err = canvas_client._canvas_send(
                "POST", f"/api/v1/courses/{cid}/modules/{mid}/items",
                {"module_item": item})

            if err:
                if _is_uncertain(err):
                    step2["state"] = "sent_unknown"
                    step2["error_code"] = "timeout_or_disconnect"
                    step2["private_diagnostic"] = err
                else:
                    step2["state"] = "failed"
                    step2["error_code"] = "module_item_rejected"
                    step2["private_diagnostic"] = err
                step2["updated_at"] = models.now_iso()
                steps.append(step2)
                return _build_result("sent_unknown", steps=steps,
                                    returned_object_id=page_slug,
                                    returned_object_url=page_url if step1["state"] == "applied" else None,
                                    error_code=step2.get("error_code"))
            else:
                step2["state"] = "applied"
                step2["updated_at"] = models.now_iso()
                steps.append(step2)

        # All steps applied → target applied
        page_url = None
        if step1["state"] == "applied":
            # Re-fetch to get html_url if we created it
            page_url = _get_page_html_url(cid, page_slug)
        elif step1["state"] == "skipped" and target.get("returned_object_url"):
            page_url = target.get("returned_object_url")

        return _build_result("applied", steps=steps,
                            returned_object_id=page_slug,
                            returned_object_url=page_url)

    # ── Reconcile ────────────────────────────────────────────────────────

    def reconcile(self, payload: dict, target: dict, baseline: dict) -> dict:
        """On restart, prove whether a sent_unknown target was applied or not.

        Same-title matching is never proof. Only exact ID or kind-specific
        postcondition.
        """
        cid = target["course_id"]
        page_slug = target.get("returned_object_id")

        if page_slug:
            # We have a page slug from a previous attempt — verify by exact ID
            page, err = canvas_client._canvas_get(
                f"/api/v1/courses/{cid}/pages/{page_slug}")
            if not err and page:
                return {"state": "applied", "returned_object_id": page_slug,
                        "returned_object_url": page.get("html_url")}
            if err and "404" in str(err):
                return {"state": "pending"}  # page was not created
            # Can't verify → stays sent_unknown
            return {"state": "sent_unknown"}

        # No returned_object_id — search by title
        title = payload.get("title", "")
        pages, err = canvas_client._canvas_get(
            f"/api/v1/courses/{cid}/pages",
            params={"per_page": 100, "search_term": title})

        if err:
            return {"state": "sent_unknown"}  # Canvas call failed

        # If no exact title match, the page was likely not created
        for page in _as_list(pages):
            if str(page.get("title", "")).strip().lower() == title.strip().lower():
                # Same-title match exists — but same-title is NEVER proof.
                # Target stays sent_unknown.
                return {"state": "sent_unknown"}

        # No exact title match → page was likely not created
        return {"state": "pending"}

    # ── Retry selector ───────────────────────────────────────────────────

    def retry_selector(self, operation: dict) -> list[dict]:
        """Return only the targets that are unresolved."""
        return [t for t in operation.get("targets", [])
                if models.is_unresolved_target_state(t.get("state", "pending"))]

    # ── Reversal ─────────────────────────────────────────────────────────

    def reversal_descriptor(self, payload: dict, target: dict) -> dict:
        """Page deletion is possible but not validated in this slice → unsupported."""
        return {"supported": False, "method": None, "snapshot": None}


# ── Helpers ──────────────────────────────────────────────────────────────

def _as_list(data) -> list:
    """Coerce a Canvas API response into a list. Handles None, dict, and list."""
    if data is None:
        return []
    if isinstance(data, list):
        return data
    return [data]


def _normalize_title(title: str) -> str:
    return str(title or "").strip().lower()


def _is_uncertain(error: str) -> bool:
    """Heuristic: is this error a timeout/disconnect/unparseable response?"""
    if not error:
        return False
    lower = error.lower()
    return any(kw in lower for kw in (
        "timeout", "timed out", "connection", "network",
        "unparseable", "no response", "read timed out",
    ))


def _find_or_create_module_id(course_id: str, name: str) -> str | None:
    """Find or create a Canvas module by name. Returns module ID or None."""
    data, err = canvas_client._canvas_get_all(
        f"/api/v1/courses/{course_id}/modules", {"per_page": 100})
    if not err:
        for m in (data or []):
            if str(m.get("name", "")).strip().lower() == name.strip().lower():
                return m.get("id")
    created, cerr = canvas_client._canvas_send(
        "POST", f"/api/v1/courses/{course_id}/modules", {"module": {"name": name}})
    if cerr:
        return None
    return created.get("id")


def _get_page_html_url(course_id: str, page_slug: str) -> str | None:
    """Fetch the html_url for a page by slug."""
    if not page_slug:
        return None
    page, err = canvas_client._canvas_get(
        f"/api/v1/courses/{course_id}/pages/{page_slug}")
    if err or not page:
        return None
    return page.get("html_url")


def _build_result(state: str, *, steps: list[dict] | None = None,
                  returned_object_id: str | None = None,
                  returned_object_url: str | None = None,
                  error_code: str | None = None,
                  private_diagnostic: str | None = None) -> dict:
    return {
        "state": state,
        "returned_object_id": returned_object_id,
        "returned_object_url": returned_object_url,
        "error_code": error_code,
        "private_diagnostic": private_diagnostic,
        "steps": steps or [],
    }
