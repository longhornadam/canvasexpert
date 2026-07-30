"""Local validation and immutable storage for Glass panes and scenes."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import jsonschema

PANE_FORMAT = "canvasexpert.glass_pane/1"
SCENE_FORMAT = "canvasexpert.glass_scene/1"
_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_MEDIA = {"image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml", "font/woff", "font/woff2"}
_MAX_ASSET, _MAX_PACKAGE = 5 * 1024 * 1024, 20 * 1024 * 1024
_SIGNATURES = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff", "image/gif": b"GIF8", "image/webp": b"RIFF", "font/woff": b"wOFF", "font/woff2": b"wOF2"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def _roots(root: str | None = None):
    if root is None:
        from api.webui import workspace
        root = workspace.workspace_root()
    if not root:
        return None, None
    base = Path(root)
    return base / "To Review" / "Glass", base / "Library" / "Glass"


def _write(path: Path, payload: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".glass-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def _read(path: Path | None):
    try:
        value = json.loads(path.read_text(encoding="utf-8")) if path and path.is_file() else None
    except (OSError, ValueError): value = None
    return value if isinstance(value, dict) else None


def _issue(errors, field, message): errors.append({"field": field, "message": message})


def _network_free(value: str, field: str, errors):
    lowered = value.lower()
    if re.search(r"(?:https?:|//)[^\s'\"<>)]+", lowered) or re.search(r"url\(\s*['\"]?(?!data:|blob:|asset:)", lowered):
        _issue(errors, field, "external URLs are not allowed")
    if field == "pane_html":
        for match in re.finditer(r"\b(src|srcset|href|action|formaction|poster)\s*=\s*(?:(['\"])(.*?)\2|([^\s>]+))", value, re.I | re.S):
            attribute, raw = match.group(1).lower(), (match.group(3) if match.group(2) else match.group(4)).strip().lower()
            if attribute == "srcset" and not raw.startswith("data:"):
                allowed = bool(raw) and all(part.strip().split()[0].startswith(("blob:", "asset:")) for part in raw.split(",") if part.strip())
            else:
                allowed = raw.startswith(("data:", "blob:", "asset:")) or (attribute == "href" and raw.startswith("#"))
            if not allowed:
                _issue(errors, field, "URL-bearing attributes must use local pane sources")
                break
    if field == "pane_css":
        for match in re.finditer(r"@import\s+(?:url\(\s*)?['\"]?([^'\"\s)]+)", value, re.I):
            if not match.group(1).lower().startswith(("data:", "blob:", "asset:")):
                _issue(errors, field, "imports must use local pane sources")
                break
    if re.search(r"\b(fetch|xmlhttprequest|websocket|eventsource)\b", lowered):
        _issue(errors, field, "network primitives are not allowed")


def _media_matches(media: str, data: bytes) -> bool:
    if media == "image/svg+xml":
        try:
            import xml.etree.ElementTree as element_tree
            text = data.decode("utf-8").lstrip()
            if re.search(r"<!doctype|<!entity", text, re.I): return False
            root = element_tree.fromstring(text)
        except (UnicodeDecodeError, ValueError, element_tree.ParseError): return False
        if root.tag.rsplit("}", 1)[-1].lower() != "svg": return False
        forbidden = {"script", "foreignobject", "iframe", "object", "embed"}
        for node in root.iter():
            if node.tag.rsplit("}", 1)[-1].lower() in forbidden: return False
            for key, value in node.attrib.items():
                name, value = key.rsplit("}", 1)[-1].lower(), value.strip().lower()
                if name.startswith("on") or value.startswith("javascript:"): return False
                if name in {"href", "src"} and not (value.startswith("#") or value.startswith("data:")): return False
                if name == "style" and re.search(r"@import|url\(\s*['\"]?(?!data:|#)", value): return False
        return not re.search(r"@import|url\(\s*['\"]?(?!data:|#)", text, re.I)
    signature = _SIGNATURES.get(media)
    return bool(signature and data.startswith(signature) and (media != "image/webp" or data[8:12] == b"WEBP"))


def validate_pane(payload: dict[str, Any]):
    errors = []
    manifest = payload.get("manifest") if isinstance(payload, dict) else None
    if not isinstance(manifest, dict): return [{"field": "manifest", "message": "must be an object"}], None
    required = {"format", "id", "title", "description", "data_schema", "example_data"}
    if set(manifest) != required: _issue(errors, "manifest", "must have exactly the pane manifest keys")
    if manifest.get("format") != PANE_FORMAT: _issue(errors, "manifest.format", f"must be {PANE_FORMAT}")
    if not isinstance(manifest.get("id"), str) or not _ID.fullmatch(manifest["id"]): _issue(errors, "manifest.id", "must be stable kebab-case")
    for field in ("title", "description"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip(): _issue(errors, f"manifest.{field}", "must be non-empty text")
    if not isinstance(manifest.get("data_schema"), dict): _issue(errors, "manifest.data_schema", "must be a JSON Schema object")
    else:
        try:
            jsonschema.Draft202012Validator.check_schema(manifest["data_schema"])
            jsonschema.Draft202012Validator(manifest["data_schema"]).validate(manifest.get("example_data"))
        except jsonschema.exceptions.SchemaError as exc: _issue(errors, "manifest.data_schema", exc.message)
        except jsonschema.ValidationError as exc: _issue(errors, "manifest.example_data", exc.message)
    for key in ("pane_html", "pane_css", "pane_js"):
        value = payload.get(key, "")
        if not isinstance(value, str) or (key == "pane_html" and not value.strip()): _issue(errors, key, "must be text" if key != "pane_html" else "must be non-empty text")
        elif isinstance(value, str): _network_free(value, key, errors)
    raw_assets = payload.get("assets", [])
    if not isinstance(raw_assets, list) or len(raw_assets) > 20: _issue(errors, "assets", "must contain zero to twenty assets"); raw_assets = []
    assets, names, size = [], set(), len(_canonical(manifest)) + sum(len(value.encode()) for value in (payload.get(key, "") for key in ("pane_html", "pane_css", "pane_js")) if isinstance(value, str))
    for index, asset in enumerate(raw_assets):
        field = f"assets[{index}]"
        if not isinstance(asset, dict): _issue(errors, field, "must be an object"); continue
        name, media, encoded = asset.get("name"), asset.get("media_type"), asset.get("data_base64")
        if not isinstance(name, str) or not _NAME.fullmatch(name) or ".." in name: _issue(errors, f"{field}.name", "must be a safe name"); continue
        if name.casefold() in names: _issue(errors, f"{field}.name", "duplicates another asset"); continue
        names.add(name.casefold())
        if media not in _MEDIA: _issue(errors, f"{field}.media_type", "is not an allowed media type")
        try: data = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError): data = b""; _issue(errors, f"{field}.data_base64", "is invalid base64")
        if len(data) > _MAX_ASSET: _issue(errors, f"{field}.data_base64", "decoded asset exceeds 5 MiB")
        if media in _MEDIA and not _media_matches(media, data): _issue(errors, f"{field}.media_type", "does not match decoded asset content")
        size += len(data); assets.append({"name": name, "media_type": media, "data_base64": base64.b64encode(data).decode()})
    if size > _MAX_PACKAGE: _issue(errors, "assets", "decoded package exceeds 20 MiB")
    if errors: return errors, None
    return [], {"manifest": manifest, "pane_html": payload["pane_html"], "pane_css": payload.get("pane_css", ""), "pane_js": payload.get("pane_js", ""), "assets": assets}


def pane_digest(pane):
    h = hashlib.sha256(); h.update(_canonical(pane["manifest"]))
    for name in ("pane_html", "pane_css", "pane_js"): h.update(name.encode() + b"\0" + pane[name].encode())
    for asset in sorted(pane["assets"], key=lambda a: a["name"].casefold()): h.update(asset["name"].encode() + b"\0" + asset["media_type"].encode() + b"\0" + base64.b64decode(asset["data_base64"]))
    return h.hexdigest()


def _draft_path(kind, key, root=None):
    review, _ = _roots(root); return review / kind / f"{key}.json" if review else None


def save_pane_draft(payload, draft_id="", root=None):
    errors, pane = validate_pane(payload)
    if errors: return {"ok": False, "errors": errors}
    path = _draft_path("panes", pane["manifest"]["id"], root)
    if path is None: return {"ok": False, "error": "workspace is unavailable"}
    old = _read(path)
    if old and old.get("draft_id") != draft_id: return {"ok": False, "errors": [{"field": "draft_id", "message": "is required and must name the existing pending pane draft"}]}
    if draft_id and not old: return {"ok": False, "errors": [{"field": "draft_id", "message": "does not name a pending pane draft"}]}
    draft_id = old.get("draft_id") if old else uuid.uuid4().hex
    record = {"kind": "pane", "draft_id": draft_id, "digest": pane_digest(pane), "pane": pane}; _write(path, _canonical(record))
    return {"ok": True, "draft_id": draft_id, "pane_id": pane["manifest"]["id"], "digest": record["digest"]}


def _approved(pane_id, revision, root=None):
    _, library = _roots(root)
    if not library or not isinstance(pane_id, str) or not _ID.fullmatch(pane_id) or not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{64}", revision): return None
    folder = library / "panes" / pane_id / revision; package = _read(folder / "package.json")
    if not _ID.fullmatch(pane_id) or not re.fullmatch(r"[0-9a-f]{64}", revision): return None
    if not package or set(package) != {"digest", "manifest", "assets"} or package.get("digest") != revision or not isinstance(package.get("manifest"), dict) or package["manifest"].get("id") != pane_id or not isinstance(package.get("assets"), list): return None
    try:
        pane = {"manifest": package["manifest"], "pane_html": (folder / "pane.html").read_text(encoding="utf-8"), "pane_css": (folder / "pane.css").read_text(encoding="utf-8") if (folder / "pane.css").is_file() else "", "pane_js": (folder / "pane.js").read_text(encoding="utf-8") if (folder / "pane.js").is_file() else "", "assets": []}
        names = set()
        for asset in package["assets"]:
            if not isinstance(asset, dict) or set(asset) != {"name", "media_type"} or not isinstance(asset["name"], str) or not _NAME.fullmatch(asset["name"]) or ".." in asset["name"] or asset.get("media_type") not in _MEDIA or asset["name"].casefold() in names: return None
            names.add(asset["name"].casefold()); pane["assets"].append({**asset, "data_base64": base64.b64encode((folder / "assets" / asset["name"]).read_bytes()).decode()})
    except (OSError, KeyError, TypeError): return None
    errors, normalized = validate_pane(pane)
    if errors or normalized is None or pane_digest(normalized) != revision: return None
    return {"digest": revision, "pane": normalized}


def _block_ids(root=None):
    from api.schedule import loader
    schedule, _ = loader.discover_bell_schedule(root)
    return set() if schedule is None else {block.block_id for day in schedule.day_types.values() for block in day.walk()}


def validate_scene(scene, root=None, block_ids=None, verify_references=True):
    errors = []
    if not isinstance(scene, dict): return [{"field": "scene", "message": "must be an object"}]
    allowed = {"format", "date", "title", "default", "blocks"}
    if set(scene) - allowed: _issue(errors, "scene", "contains unknown keys")
    for key in ("format", "date", "title", "default"):
        if key not in scene: _issue(errors, key, "is required")
    if scene.get("format") != SCENE_FORMAT: _issue(errors, "format", f"must be {SCENE_FORMAT}")
    try: date.fromisoformat(str(scene.get("date", "")))
    except ValueError: _issue(errors, "date", "must be YYYY-MM-DD")
    if not isinstance(scene.get("title"), str) or not scene["title"].strip(): _issue(errors, "title", "must be non-empty text")
    blocks = scene.get("blocks", {})
    if not isinstance(blocks, dict): _issue(errors, "blocks", "must be an object"); blocks = {}
    layouts = {"default": scene.get("default")}; layouts.update({f"blocks.{key}": value for key, value in blocks.items()})
    for label, instances in layouts.items():
        block_id = label.removeprefix("blocks.")
        if label != "default" and block_ids is not None and block_id not in block_ids: _issue(errors, label, "is not a bell-schedule block id")
        if not isinstance(instances, list): _issue(errors, label, "must be a complete list"); continue
        used, ids = set(), set()
        for index, instance in enumerate(instances):
            field = f"{label}[{index}]"
            expected = {"instance_id", "pane_id", "pane_revision", "data", "column", "row", "width", "height"}
            if not isinstance(instance, dict) or set(instance) != expected: _issue(errors, field, "must have exactly the instance keys"); continue
            if not isinstance(instance["instance_id"], str) or not instance["instance_id"] or instance["instance_id"] in ids: _issue(errors, f"{field}.instance_id", "must be unique")
            ids.add(instance["instance_id"]); pane = _approved(instance["pane_id"], instance["pane_revision"], root)
            if not isinstance(instance["pane_id"], str) or not _ID.fullmatch(instance["pane_id"]): _issue(errors, f"{field}.pane_id", "must be a pane id")
            if not isinstance(instance["pane_revision"], str) or not re.fullmatch(r"[0-9a-f]{64}", instance["pane_revision"]): _issue(errors, f"{field}.pane_revision", "must be a pane revision")
            if verify_references and not pane: _issue(errors, f"{field}.pane_revision", "must name an approved pane revision")
            elif verify_references:
                try: jsonschema.Draft202012Validator(pane["pane"]["manifest"]["data_schema"]).validate(instance["data"])
                except jsonschema.ValidationError as exc: _issue(errors, f"{field}.data", exc.message)
            values = [instance[key] for key in ("column", "row", "width", "height")]
            if not all(isinstance(item, int) and not isinstance(item, bool) for item in values): _issue(errors, field, "grid coordinates must be integers"); continue
            col, row, width, height = values
            if min(values) < 1 or col + width > 13 or row + height > 9: _issue(errors, field, "placement is outside the 12 by 8 grid"); continue
            for cell in ((x, y) for x in range(col, col + width) for y in range(row, row + height)):
                if cell in used: _issue(errors, field, "placement overlaps another instance"); break
                used.add(cell)
    return errors


def _scene_digest(scene):
    return hashlib.sha256(_canonical(scene)).hexdigest()


def save_scene_draft(scene, draft_id="", root=None):
    errors = validate_scene(scene, root, _block_ids(root))
    if errors: return {"ok": False, "errors": errors}
    path = _draft_path("scenes", scene["date"], root)
    if path is None: return {"ok": False, "error": "workspace is unavailable"}
    old = _read(path)
    if old and old.get("draft_id") != draft_id: return {"ok": False, "errors": [{"field": "draft_id", "message": "is required and must name the existing pending scene draft"}]}
    if draft_id and not old: return {"ok": False, "errors": [{"field": "draft_id", "message": "does not name a pending scene draft"}]}
    draft_id = old.get("draft_id") if old else uuid.uuid4().hex; digest = _scene_digest(scene)
    _write(path, _canonical({"kind": "scene", "draft_id": draft_id, "digest": digest, "scene": scene}))
    return {"ok": True, "draft_id": draft_id, "date": scene["date"], "digest": digest}


def _draft_records(review):
    if not review:
        return
    for directory in (review / "panes", review / "scenes"):
        for path in directory.glob("*.json") if directory.is_dir() else ():
            record = _read(path)
            if not isinstance(record, dict) or not isinstance(record.get("draft_id"), str) or not re.fullmatch(r"[0-9a-f]{32}", record["draft_id"]):
                continue
            if not isinstance(record.get("digest"), str) or not re.fullmatch(r"[0-9a-f]{64}", record["digest"]):
                continue
            if record.get("kind") == "pane":
                if set(record) != {"kind", "draft_id", "digest", "pane"} or not isinstance(record.get("pane"), dict) or set(record["pane"]) != {"manifest", "pane_html", "pane_css", "pane_js", "assets"}:
                    continue
                errors, pane = validate_pane(record["pane"])
                if errors or pane is None or pane_digest(pane) != record["digest"] or path.stem != pane["manifest"]["id"]:
                    continue
                yield path, record
            elif record.get("kind") == "scene":
                scene = record.get("scene")
                if set(record) != {"kind", "draft_id", "digest", "scene"} or not isinstance(scene, dict):
                    continue
                if not isinstance(scene.get("date"), str) or path.stem != scene["date"] or _scene_digest(scene) != record["digest"]:
                    continue
                try:
                    date.fromisoformat(scene["date"])
                except ValueError:
                    continue
                allowed = {"format", "date", "title", "default", "blocks"}
                blocks = scene.get("blocks")
                if set(scene) - allowed or not isinstance(scene.get("default"), list) or not isinstance(blocks, dict):
                    continue
                if any(not isinstance(instances, list) or any(not isinstance(instance, dict) for instance in instances)
                       for instances in [scene["default"], *blocks.values()]):
                    continue
                yield path, record


def draft(draft_id, root=None):
    review, _ = _roots(root)
    if isinstance(draft_id, str) and re.fullmatch(r"[0-9a-f]{32}", draft_id):
        for _, record in _draft_records(review):
            if record["draft_id"] == draft_id: return record
    return None


def list_drafts(root=None):
    review, _ = _roots(root); result = []
    if review:
        for _, record in _draft_records(review):
            if record:
                subject = record.get("pane", {}).get("manifest", {}).get("id") if record.get("kind") == "pane" else record.get("scene", {}).get("date")
                result.append({"draft_id": record.get("draft_id"), "kind": record.get("kind"), "subject": subject, "digest": record.get("digest")})
    return sorted(result, key=lambda row: (row["kind"], str(row["subject"])))


def discard(draft_id, root=None):
    review, _ = _roots(root)
    if isinstance(draft_id, str) and re.fullmatch(r"[0-9a-f]{32}", draft_id):
        for path, record in _draft_records(review):
            if record["draft_id"] == draft_id: path.unlink(); return True
    return False


def approve_pane(draft_id, digest, root=None):
    record = draft(draft_id, root)
    if not record or record.get("kind") != "pane": return {"ok": False, "error": "pending pane draft not found"}
    errors, pane = validate_pane(record.get("pane", {})); actual = pane_digest(pane) if pane else ""
    if errors or digest != record.get("digest") or actual != digest: return {"ok": False, "error": "draft changed or invalid", "errors": errors}
    _, library = _roots(root); destination = library / "panes" / pane["manifest"]["id"] / digest
    if destination.exists() and _approved(pane["manifest"]["id"], digest, root) is None:
        return {"ok": False, "error": "existing approved pane revision is corrupted"}
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True); temp = Path(tempfile.mkdtemp(prefix=".glass-pane-", dir=destination.parent))
        try:
            _write(temp / "package.json", _canonical({"digest": digest, "manifest": pane["manifest"], "assets": [{"name": item["name"], "media_type": item["media_type"]} for item in pane["assets"]]}))
            for key, name in (("pane_html", "pane.html"), ("pane_css", "pane.css"), ("pane_js", "pane.js")):
                if pane[key]: _write(temp / name, pane[key].encode())
            for asset in pane["assets"]: _write(temp / "assets" / asset["name"], base64.b64decode(asset["data_base64"]))
            os.replace(temp, destination)
        finally:
            if temp.exists(): shutil.rmtree(temp, ignore_errors=True)
    discard(draft_id, root); return {"ok": True, "pane_id": pane["manifest"]["id"], "pane_revision": digest}


def approve_scene(draft_id, digest, root=None):
    record = draft(draft_id, root)
    if not record or record.get("kind") != "scene": return {"ok": False, "error": "pending scene draft not found"}
    scene = record.get("scene", {}); errors = validate_scene(scene, root, _block_ids(root)); actual = _scene_digest(scene)
    if errors or digest != record.get("digest") or actual != digest: return {"ok": False, "error": "draft changed or invalid", "errors": errors}
    _, library = _roots(root); _write(library / "scenes" / f"{scene['date']}.json", _canonical({"digest": digest, "scene": scene}))
    discard(draft_id, root); return {"ok": True, "date": scene["date"], "digest": digest}


def list_approved(root=None):
    """Approved pane revisions and scenes that still read back intact."""
    _, library = _roots(root); result = {"panes": [], "scenes": []}
    if not library: return result
    for pane_folder in sorted((library / "panes").iterdir()) if (library / "panes").is_dir() else ():
        for revision_folder in sorted(pane_folder.iterdir()) if pane_folder.is_dir() else ():
            package = _approved(pane_folder.name, revision_folder.name, root) if revision_folder.is_dir() else None
            if package:
                manifest = package["pane"]["manifest"]
                result["panes"].append({"pane_id": manifest["id"], "revision": package["digest"], "title": manifest["title"], "description": manifest["description"], "data_schema": manifest["data_schema"]})
    for path in sorted((library / "scenes").glob("*.json")) if (library / "scenes").is_dir() else ():
        try: day = date.fromisoformat(path.stem)
        except ValueError: continue
        record = approved_scene(day, root)
        if record: result["scenes"].append({"date": path.stem, "digest": record["digest"], "title": record["scene"].get("title")})
    return result


def approved_scene(day, root=None):
    _, library = _roots(root)
    if not library or not isinstance(day, date): return None
    record = _read(library / "scenes" / f"{day.isoformat()}.json")
    if not record or set(record) != {"digest", "scene"} or not isinstance(record.get("digest"), str) or not re.fullmatch(r"[0-9a-f]{64}", record["digest"]) or not isinstance(record.get("scene"), dict): return None
    scene = record["scene"]
    if scene.get("date") != day.isoformat() or _scene_digest(scene) != record["digest"] or validate_scene(scene, root, verify_references=False): return None
    return record
