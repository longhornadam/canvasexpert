"""Layout and text helpers for PowerGrader Copilot batch packets."""

from __future__ import annotations

import json
import os

from api import feedback_contract
from api.webui import workspace


def write_text(path: str, text: str) -> None:
    os.makedirs(workspace.extended_path(os.path.dirname(path)), exist_ok=True)
    with open(workspace.extended_path(path), "w", encoding="utf-8") as f:
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
    rubric = (rubric_text or "").strip()
    contract = feedback_contract.scoring_output_contract(
        persona=persona,
        ai_ta_name=ta_name,
        identity_source="StudentWork",
        pseudonym="<copy from StudentWork exactly>",
        item_id="<copy from StudentWork exactly>",
        include_signoff_in_feedback=True,
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
        f"{contract['format_instruction']}\n\n"
        "```json\n"
        f"{json.dumps(contract['sample'], indent=2, ensure_ascii=False)}\n"
        "```\n\n"
        "Rules:\n\n"
        f"{contract['rules_text']}\n"
        "- Score only students in file 03.\n"
        "- Do not mention real names.\n"
    )


def batch_prompt(
    batch_number: int,
    total_batches: int,
    persona: dict | None = None,
) -> str:
    contract = feedback_contract.scoring_output_contract(
        persona=persona,
        identity_source="StudentWork",
        pseudonym="<copy>",
        item_id="<copy>",
    )
    return (
        "Use the three uploaded files in order: 01 Assignment Information, 02 Rubric and TA "
        f"Personality, and 03 StudentWork for Batch {batch_number} of {total_batches}.\n\n"
        f"Score only the students listed in the StudentWork file for Batch {batch_number} of "
        f"{total_batches}. Do not score students from any other batch.\n\n"
        f"{contract['format_instruction']}\n\n"
        f"```json\n{json.dumps(contract['sample'], indent=2, ensure_ascii=False)}\n```\n\n"
        f"Rules:\n{contract['rules_text']}"
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
