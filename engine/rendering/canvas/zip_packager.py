"""ZIP packaging helpers."""

from __future__ import annotations

import io
import zipfile


def create_zip_bytes(manifest_xml: str, assessment_xml: str, assessment_meta_xml: str, guid: str) -> bytes:
    """Create QTI package as bytes (for web download)."""
    folder = guid
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("imsmanifest.xml", manifest_xml.encode("utf-8"))
        archive.writestr(f"{folder}/{guid}.xml", assessment_xml.encode("utf-8"))
        archive.writestr(f"{folder}/assessment_meta.xml", assessment_meta_xml.encode("utf-8"))
    return buffer.getvalue()