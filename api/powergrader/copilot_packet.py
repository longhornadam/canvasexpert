"""Copilot batch packet builder for PowerGrader Safe AI Packet artifacts."""

from __future__ import annotations

import os

from webui.source_materials import estimate_text_tokens

try:
    import feedback_pipeline as fp
except ModuleNotFoundError:
    from api import feedback_pipeline as fp

from .packet import safe_ai_packet_name


DEFAULT_COPILOT_CONTEXT_TOKENS = 128_000
COPILOT_OUTPUT_RESERVE_TOKENS = 24_000
COPILOT_SAFETY_MARGIN_TOKENS = 8_000
MIN_STUDENTWORK_TOKENS = 20_000
PACKET_VERSION = 1

_LARGE_CONTEXT_WARNING = (
    "Assignment information plus rubric/persona is large; Copilot may miss student work. "
    "Consider shorter context or API scoring."
)
_OVERSIZED_STUDENT_WARNING = (
    "This one student's SAFE work is larger than the target Copilot budget. "
    "Score this batch carefully or manually."
)


def _safe_assignment_name(assignment_name: str) -> str:
    packet_name = safe_ai_packet_name(assignment_name)
    prefix = "Safe AI Packet - "
    if packet_name.startswith(prefix):
        return packet_name[len(prefix):]
    return packet_name


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _assignment_info_text(assignment_name: str, llm_bundle: dict) -> str:
    shared = (llm_bundle or {}).get("shared_context") or {}
    assignment_description = (shared.get("assignment_description") or "").strip()
    lines = [
        "# Assignment Information - SAFE",
        "",
        f"Assignment: {assignment_name}",
        "",
        "This file contains shared assignment/context material for a pseudonymized PowerGrader batch.",
        "It should be uploaded as file 01.",
        "",
        "## Assignment Directions",
        "",
        assignment_description or "No assignment directions were included.",
        "",
        "## Source Materials",
        "",
    ]
    materials = [m for m in shared.get("materials") or [] if isinstance(m, dict)]
    included = False
    for material in materials:
        text = (material.get("text") or "").strip()
        if not text:
            continue
        included = True
        title = (material.get("title") or "Source material").strip()
        source = (material.get("source") or "").strip()
        lines.extend([
            f"### {title}",
            "",
            f"Source: {source}",
            "",
            text,
            "",
        ])
    if not included:
        lines.append("No separate source material was included.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _rubric_persona_text(assignment_name: str, rubric_text: str, persona: dict) -> str:
    persona = persona or {}
    ta_name = (persona.get("name") or "").strip() or "your teaching assistant"
    personality = (persona.get("personality") or "").strip()
    signoff = fp.persona_signoff(persona, ta_name)
    rubric = (rubric_text or "").strip()
    feedback_hint = "Brief rubric-based feedback."
    disclosure_line = ""
    signoff_rule = "- Do not add a separate signature or disclosure beyond the selected persona.\n"
    if signoff:
        feedback_hint = "Brief rubric-based feedback. End with the persona signoff exactly once."
        disclosure_line = f',\n  "disclosure": "{signoff}"'
        signoff_rule = (
            f"- End feedback with this persona signoff exactly once: {signoff}\n"
            "- Do not add a separate signature or disclosure.\n"
        )
    return (
        "# Rubric and TA Personality - SAFE\n\n"
        f"Assignment: {assignment_name}\n\n"
        "This file contains scoring instructions for a pseudonymized PowerGrader batch.\n"
        "It should be uploaded as file 02.\n\n"
        "## AI Teaching Assistant Personality\n\n"
        f"Name: {ta_name}\n\n"
        f"{personality or 'Use a clear, supportive, rubric-based teacher voice.'}\n\n"
        "## Rubric\n\n"
        f"{rubric or 'No rubric text was provided. Use the assignment point value and teacher directions.'}\n\n"
        "## Required JSON Output\n\n"
        "Return only a JSON array. Each element must be exactly:\n\n"
        "```json\n"
        "{\n"
        '  "pseudonym": "<copy from StudentWork exactly>",\n'
        '  "item_id": "<copy from StudentWork exactly>",\n'
        '  "score": 2,\n'
        f'  "feedback": "{feedback_hint}"{disclosure_line}\n'
        "}\n"
        "```\n\n"
        "Rules:\n\n"
        "- Score only students in file 03.\n"
        "- Copy `pseudonym` and `item_id` exactly.\n"
        "- `score` may be a number or null.\n"
        "- `feedback` must be non-empty.\n"
        f"{signoff_rule}"
        "- Do not identify students.\n"
        "- Do not mention real names.\n"
    )


def _student_blocks(llm_bundle: dict) -> list[dict]:
    blocks: list[dict] = []
    ordinal = 1
    for student in (llm_bundle or {}).get("students") or []:
        pseudonym = str(student.get("pseudonym") or "Unknown")
        responses = student.get("responses") or [{}]
        for response in responses:
            item_id = str(response.get("item_id") or "")
            possible = response.get("possible")
            text = str(response.get("response") or "").strip()
            block = (
                f"## Student {ordinal:02d}\n\n"
                f"Pseudonym: {pseudonym}\n"
                f"Item ID: {item_id}\n"
                f"Possible points: {possible if possible is not None else ''}\n\n"
                "### Response\n\n"
                f"{text or 'No text response was available in the SAFE packet.'}\n"
            )
            blocks.append({
                "pseudonym": pseudonym,
                "item_id": item_id,
                "text": block,
                "tokens": estimate_text_tokens(block),
            })
            ordinal += 1
    return blocks


def _batch_prompt(batch_number: int, total_batches: int) -> str:
    return (
        "Use the three uploaded files in order: 01 Assignment Information, 02 Rubric and TA "
        f"Personality, and 03 StudentWork for Batch {batch_number} of {total_batches}.\n\n"
        f"Score only the students listed in the StudentWork file for Batch {batch_number} of "
        f"{total_batches}. Do not score students from any other batch.\n\n"
        "Return only valid JSON. Return a JSON array only, with one object per scored student. "
        "Copy pseudonym and item_id exactly from StudentWork."
    )


def _student_work_text(
    *,
    assignment_name: str,
    batch_number: int,
    total_batches: int,
    entries: list[dict],
) -> str:
    lines = [
        f"# StudentWork - SAFE - Batch {batch_number:02d} of {total_batches:02d}",
        "",
        f"Assignment: {assignment_name}",
        f"Batch: {batch_number:02d} of {total_batches:02d}",
        f"Student count in this file: {len(entries)}",
        "",
        "Score only the students in this file.",
        "Do not score students from another batch.",
        "",
    ]
    lines.extend(entry["text"].rstrip() + "\n" for entry in entries)
    return "\n".join(lines).rstrip() + "\n"


def _split_batches(student_blocks: list[dict], available_studentwork_tokens: int) -> list[dict]:
    batches: list[dict] = []
    current: list[dict] = []
    current_tokens = 0
    target = max(1, available_studentwork_tokens)

    for block in student_blocks:
        block_tokens = block["tokens"]
        if current and current_tokens + block_tokens > target:
            batches.append({"entries": current, "warnings": []})
            current = []
            current_tokens = 0
        warnings = [_OVERSIZED_STUDENT_WARNING] if block_tokens > target else []
        if warnings:
            if current:
                batches.append({"entries": current, "warnings": []})
                current = []
                current_tokens = 0
            batches.append({"entries": [block], "warnings": warnings})
            continue
        current.append(block)
        current_tokens += block_tokens

    if current or not batches:
        batches.append({"entries": current, "warnings": []})
    return batches


def build_copilot_batches(
    *,
    assignment_name: str,
    safe_dir: str,
    llm_bundle: dict,
    rubric_text: str,
    persona: dict,
    effective_context_tokens: int = DEFAULT_COPILOT_CONTEXT_TOKENS,
    output_reserve_tokens: int = COPILOT_OUTPUT_RESERVE_TOKENS,
    safety_margin_tokens: int = COPILOT_SAFETY_MARGIN_TOKENS,
) -> dict:
    """Build fresh-chat Copilot batch folders from a SAFE LLM bundle."""
    safe_dir = os.path.abspath(safe_dir)
    safe_name = _safe_assignment_name(assignment_name)
    packet_folder = os.path.abspath(os.path.join(safe_dir, safe_ai_packet_name(assignment_name), "Copilot Batches"))
    os.makedirs(packet_folder, exist_ok=True)

    file_01_text = _assignment_info_text(assignment_name, llm_bundle)
    file_02_text = _rubric_persona_text(assignment_name, rubric_text, persona)
    fixed_context_tokens = (
        estimate_text_tokens(file_01_text)
        + estimate_text_tokens(file_02_text)
        + estimate_text_tokens(_batch_prompt(1, 1))
    )
    available = effective_context_tokens - output_reserve_tokens - safety_margin_tokens - fixed_context_tokens
    warnings: list[str] = []
    if available < MIN_STUDENTWORK_TOKENS:
        warnings.append(_LARGE_CONTEXT_WARNING)

    student_blocks = _student_blocks(llm_bundle)
    raw_batches = _split_batches(student_blocks, available)
    total_batches = len(raw_batches)
    batches: list[dict] = []

    readme_path = os.path.join(packet_folder, "README - Copilot Steps.md")
    readme_lines = [
        "# Copilot Steps",
        "",
        "This is one PowerGrader session. Do not start a new PowerGrader session for each batch.",
        "",
        "For each batch:",
        "",
        "1. Start a new Copilot chat.",
        "2. Upload files 01, 02, and 03 from that batch folder.",
        "3. Paste the batch prompt from PowerGrader.",
        "4. Copy Copilot's JSON response.",
        "5. Return to the same PowerGrader session.",
        "6. Paste results into the matching batch import box.",
        "7. Continue with the next batch.",
        "",
        f"Assignment: {assignment_name}",
        "",
    ]

    for index, raw_batch in enumerate(raw_batches, start=1):
        label = f"Batch {index} of {total_batches}"
        folder = os.path.abspath(os.path.join(packet_folder, f"Batch {index:02d} of {total_batches:02d}"))
        os.makedirs(folder, exist_ok=True)

        assignment_info_path = os.path.join(folder, f"01 - {safe_name} - Assignment Information - SAFE.md")
        rubric_persona_path = os.path.join(folder, f"02 - {safe_name} - Rubric and TA Personality - SAFE.md")
        student_work_path = os.path.join(
            folder,
            f"03 - {safe_name} - StudentWork - SAFE - Batch {index:02d} of {total_batches:02d}.md",
        )
        student_work_text = _student_work_text(
            assignment_name=assignment_name,
            batch_number=index,
            total_batches=total_batches,
            entries=raw_batch["entries"],
        )
        _write_text(assignment_info_path, file_01_text)
        _write_text(rubric_persona_path, file_02_text)
        _write_text(student_work_path, student_work_text)

        prompt = _batch_prompt(index, total_batches)
        token_estimate = (
            estimate_text_tokens(file_01_text)
            + estimate_text_tokens(file_02_text)
            + estimate_text_tokens(prompt)
            + estimate_text_tokens(student_work_text)
        )
        expected_results = [
            {"pseudonym": entry["pseudonym"], "item_id": entry["item_id"]}
            for entry in raw_batch["entries"]
        ]
        batches.append({
            "batch_id": f"batch-{index:02d}",
            "label": label,
            "folder": folder,
            "files": {
                "assignment_info": assignment_info_path,
                "rubric_persona": rubric_persona_path,
                "student_work": student_work_path,
            },
            "prompt": prompt,
            "student_count": len(raw_batch["entries"]),
            "token_estimate": token_estimate,
            "expected_results": expected_results,
            "status": "pending",
            "imported_at": None,
            "updated": 0,
            "warnings": raw_batch["warnings"],
        })
        readme_lines.extend([f"## {label}", "", prompt, ""])

    _write_text(readme_path, "\n".join(readme_lines).rstrip() + "\n")

    return {
        "version": PACKET_VERSION,
        "packet_type": "copilot_batches",
        "mode": "fresh_chat_per_batch",
        "assignment_name": assignment_name,
        "packet_folder": packet_folder,
        "readme_path": os.path.abspath(readme_path),
        "budget": {
            "effective_context_tokens": effective_context_tokens,
            "output_reserve_tokens": output_reserve_tokens,
            "safety_margin_tokens": safety_margin_tokens,
            "fixed_context_tokens": fixed_context_tokens,
            "available_studentwork_tokens": available,
        },
        "batch_count": total_batches,
        "student_count": len(student_blocks),
        "batches": batches,
        "warnings": warnings,
    }
