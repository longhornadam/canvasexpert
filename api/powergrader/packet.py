"""Safe AI Packet building helpers for PowerGrader.

Creates the teacher-facing packet folder and ZIP from SAFE artifacts,
including student responses, source materials, rubric instructions, and
paste-back JSON format.
"""

import json
import os
import zipfile

import feedback_pipeline as fp


def safe_ai_packet_name(assignment_name: str) -> str:
    return f"Safe AI Packet - {fp._safe(assignment_name, max_len=60)}"


def packet_paths(safe_dir: str, assignment_name: str) -> dict:
    packet_name = safe_ai_packet_name(assignment_name)
    return {
        "name": packet_name,
        "dir": os.path.join(safe_dir, packet_name),
        "zip": os.path.join(safe_dir, f"{packet_name}.zip"),
    }


def shared_context_text(bundle: dict) -> str:
    shared = (bundle or {}).get("shared_context") or {}
    chunks: list[str] = []
    assignment_description = (shared.get("assignment_description") or "").strip()
    if assignment_description:
        chunks.append("Assignment directions/context\n" + "=" * 32 + "\n" + assignment_description)
    for material in shared.get("materials") or []:
        if not isinstance(material, dict):
            continue
        title = material.get("title") or "Source material"
        source = material.get("source") or ""
        text = (material.get("text") or "").strip()
        if not text:
            continue
        header = title + (f"\nFrom: {source}" if source else "")
        chunks.append(header + "\n" + "=" * 32 + "\n" + text)
    return "\n\n".join(chunks).strip()


def readable_responses_text(bundle: dict) -> str:
    lines = [
        "Student Responses - readable",
        "=" * 32,
        "These are fake-name copies. Do not ask the AI to identify students.",
        "",
    ]
    for student in (bundle or {}).get("students") or []:
        lines.append(f"Student: {student.get('pseudonym', 'Unknown')}")
        lines.append("-" * 32)
        for response in student.get("responses") or []:
            if response.get("item_id"):
                lines.append(f"Item ID: {response.get('item_id')}")
            if response.get("possible") is not None:
                lines.append(f"Possible points: {response.get('possible')}")
            if response.get("prompt"):
                lines.append("\nPrompt:")
                lines.append(str(response.get("prompt") or ""))
            lines.append("\nResponse:")
            lines.append(str(response.get("response") or ""))
            lines.append("")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def paste_format_text(bundle: dict, persona: dict | None = None) -> str:
    first_student = ((bundle or {}).get("students") or [{}])[0]
    first_response = ((first_student.get("responses") or [{}])[0])
    pseudonym = first_student.get("pseudonym") or "<copy pseudonym exactly>"
    item_id = first_response.get("item_id") or "<copy item_id exactly>"
    signoff = fp.persona_signoff(persona or {})
    feedback_hint = "Brief rubric-based feedback."
    if signoff:
        feedback_hint = (
            "Brief rubric-based feedback. End with the persona signoff exactly once. "
            + signoff
        )
    sample = [{
        "pseudonym": pseudonym,
        "item_id": str(item_id),
        "score": 1,
        "feedback": feedback_hint,
    }]
    if signoff:
        sample[0]["disclosure"] = signoff
    return (
        "Paste Results Back Here - Format\n"
        "================================\n\n"
        "After your AI chat scores the packet, paste ONLY the JSON array or a JSON "
        "object with a results array back into PowerGrader.\n\n"
        "Required shape:\n\n"
        + json.dumps(sample, indent=2, ensure_ascii=False)
        + "\n\nRules:\n"
        "- Copy pseudonym and item_id exactly from Student Responses.json.\n"
        "- score may be a number or null for comment-only feedback.\n"
        "- feedback must be non-empty.\n"
        "- disclosure is optional metadata; include it only when the selected persona uses a signoff.\n"
        "- PowerGrader validates this before adding AI suggestions to the session.\n"
    )


def build_safe_ai_packet(
    assignment_name: str,
    safe_dir: str,
    write_result: dict,
    llm_bundle: dict,
    persona: dict | None = None,
) -> dict:
    """Create a teacher-facing packet folder + ZIP from the SAFE artifacts."""
    paths = packet_paths(safe_dir, assignment_name)
    packet_dir = paths["dir"]
    os.makedirs(packet_dir, exist_ok=True)

    files: list[str] = []

    def write_packet_file(name: str, text: str):
        path = os.path.join(packet_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        files.append(path)

    how_to_path = write_result.get("how_to_score")
    if how_to_path and os.path.isfile(how_to_path):
        with open(how_to_path, encoding="utf-8") as f:
            instructions = f.read()
    else:
        instructions = fp.build_contract_text("your teaching assistant", persona=persona)
    write_packet_file("START HERE - Instructions for your AI.txt", instructions)

    bundle_path = os.path.join(packet_dir, "Student Responses.json")
    with open(bundle_path, "w", encoding="utf-8") as f:
        json.dump(llm_bundle, f, indent=2, ensure_ascii=False)
    files.append(bundle_path)

    write_packet_file("Student Responses - readable.txt", readable_responses_text(llm_bundle))

    shared_text = shared_context_text(llm_bundle)
    write_packet_file(
        "Source Materials.txt",
        shared_text or "No separate source material was included in this packet.\n",
    )
    write_packet_file("Paste Results Back Here - Format.txt", paste_format_text(llm_bundle, persona))

    for student_txt in write_result.get("student_txts") or []:
        if os.path.isfile(student_txt):
            dest = os.path.join(packet_dir, os.path.basename(student_txt))
            with open(student_txt, "rb") as src, open(dest, "wb") as out:
                out.write(src.read())
            files.append(dest)

    with zipfile.ZipFile(paths["zip"], "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, arcname=os.path.basename(path))

    return {
        "packet_name": paths["name"],
        "packet_folder": packet_dir,
        "packet_zip": paths["zip"],
        "packet_files": files,
    }
