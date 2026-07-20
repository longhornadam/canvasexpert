"""Layout and text helpers for PowerGrader Copilot batch packets."""

from __future__ import annotations

import os

from api import feedback_pipeline as fp


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def assignment_info_text(assignment_name: str, llm_bundle: dict) -> str:
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


def rubric_persona_text(assignment_name: str, rubric_text: str, persona: dict) -> str:
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


def batch_prompt(batch_number: int, total_batches: int) -> str:
    return (
        "Use the three uploaded files in order: 01 Assignment Information, 02 Rubric and TA "
        f"Personality, and 03 StudentWork for Batch {batch_number} of {total_batches}.\n\n"
        f"Score only the students listed in the StudentWork file for Batch {batch_number} of "
        f"{total_batches}. Do not score students from any other batch.\n\n"
        "Return only valid JSON. Return a JSON array only, with one object per scored student. "
        "Copy pseudonym and item_id exactly from StudentWork."
    )


def student_work_text(
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
