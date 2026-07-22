"""Copilot batch packet builder for PowerGrader Safe AI Packet artifacts."""

from __future__ import annotations

import os

from api.webui import workspace
from api.webui.source_materials import estimate_text_tokens

from .packet import safe_ai_packet_name
from . import copilot_packet_support as support


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


def _needs_compact_layout(safe_dir: str, packet_name: str, assignment_name: str) -> bool:
    """Determine whether the deep workspace forces compact batch layout.

    Projects the normal readable batch file path.  If it exceeds the
    230-char budget, compact layout is selected.
    """
    safe_dir = os.path.abspath(safe_dir)
    safe_name = _safe_assignment_name(assignment_name)
    normal_path = os.path.join(
        safe_dir, packet_name, "Copilot Batches",
        "Batch 99 of 99",
        f"03 - {safe_name} - StudentWork - SAFE - Batch 99 of 99.md",
    )
    return len(normal_path) > workspace.TEACHER_VISIBLE_BUDGET


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
    batch_id_prefix: str | None = None,
    safe_bundle_path: str | None = None,
    assignment_id: str = "",
) -> dict:
    """Build fresh-chat Copilot batch folders from a SAFE LLM bundle.

    Selects the normal (readable) or compact layout based on path budget.
    Compact layout uses ``Packet-<stable-id>/Batches/Batch-<n>/`` with numbered
    upload files (01-info.md, 02-rubric.md, 03-work.md) and a shorter README.

    Args:
        batch_id_prefix: Optional prefix for batch IDs (e.g. 'late-20260715-142200').
            Initial batches use 'batch-01'; late batches use '<prefix>-batch-01'.
        safe_bundle_path: Absolute path to the SAFE bundle JSON. Each batch stores
            its own absolute safe_bundle path for validation.
        assignment_id: Canvas assignment ID for stable compact identifiers.
    """
    safe_dir = os.path.abspath(safe_dir)
    safe_name = _safe_assignment_name(assignment_name)
    packet_name = safe_ai_packet_name(assignment_name, assignment_id=assignment_id)
    packet_folder = os.path.abspath(os.path.join(safe_dir, packet_name))

    # Determine if compact layout is needed by projecting batch paths.
    compact = _needs_compact_layout(safe_dir, packet_name, assignment_name)

    if compact:
        bat_container = os.path.abspath(os.path.join(safe_dir, packet_name, "Batches"))
    else:
        bat_container = os.path.abspath(os.path.join(safe_dir, packet_name, "Copilot Batches"))

    file_01_text = support.assignment_info_text(assignment_name, llm_bundle)
    file_02_text = support.rubric_persona_text(assignment_name, rubric_text, persona)
    fixed_context_tokens = (
        estimate_text_tokens(file_01_text)
        + estimate_text_tokens(file_02_text)
        + estimate_text_tokens(support.batch_prompt(1, 1))
    )
    available = effective_context_tokens - output_reserve_tokens - safety_margin_tokens - fixed_context_tokens
    warnings: list[str] = []
    if available < MIN_STUDENTWORK_TOKENS:
        warnings.append(_LARGE_CONTEXT_WARNING)

    student_blocks = _student_blocks(llm_bundle)
    raw_batches = _split_batches(student_blocks, available)
    total_batches = len(raw_batches)
    batches: list[dict] = []

    readme_path = os.path.join(bat_container, "README - Copilot Steps.md")
    if compact:
        # README is a bit shorter to keep paths within budget
        readme_path = os.path.join(bat_container, "README.md")
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
        if compact:
            label = f"Batch-{index}"
            folder = os.path.abspath(os.path.join(bat_container, f"Batch-{index}"))
        else:
            label = f"Batch {index} of {total_batches}"
            folder = os.path.abspath(os.path.join(bat_container, f"Batch {index:02d} of {total_batches:02d}"))

        os.makedirs(workspace.extended_path(folder), exist_ok=True)

        # Compute the batch_id: prefix + 'batch-XX' for late, or 'batch-XX' for initial
        if batch_id_prefix:
            batch_id_value = f"{batch_id_prefix}-batch-{index:02d}"
        else:
            batch_id_value = f"batch-{index:02d}"

        if compact:
            assignment_info_path = os.path.join(folder, "01-info.md")
            rubric_persona_path = os.path.join(folder, "02-rubric.md")
            student_work_path = os.path.join(folder, "03-work.md")
        else:
            assignment_info_path = os.path.join(folder, f"01 - {safe_name} - Assignment Information - SAFE.md")
            rubric_persona_path = os.path.join(folder, f"02 - {safe_name} - Rubric and TA Personality - SAFE.md")
            student_work_path = os.path.join(
                folder,
                f"03 - {safe_name} - StudentWork - SAFE - Batch {index:02d} of {total_batches:02d}.md",
            )

        # Validate every batch file path against the budget before writing
        for path in (assignment_info_path, rubric_persona_path, student_work_path, readme_path):
            apath = os.path.abspath(path)
            actual_len = len(apath)
            if actual_len > workspace.TEACHER_VISIBLE_BUDGET:
                raise workspace.TeacherVisiblePathBudgetError(
                    f"Batch file path exceeds budget "
                    f"({actual_len} > {workspace.TEACHER_VISIBLE_BUDGET}): {apath}"
                )

        student_work_text = support.student_work_text(
            assignment_name=assignment_name,
            batch_number=index,
            total_batches=total_batches,
            entries=raw_batch["entries"],
        )
        if compact:
            # Compact mode: student_work_text uses short label
            student_work_text = support.student_work_text(
                assignment_name=assignment_name,
                batch_number=index,
                total_batches=total_batches,
                entries=raw_batch["entries"],
            )
        support.write_text(assignment_info_path, file_01_text)
        support.write_text(rubric_persona_path, file_02_text)
        support.write_text(student_work_path, student_work_text)

        prompt = support.batch_prompt(index, total_batches)
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
            "batch_id": batch_id_value,
            "label": label,
            "folder": folder,
            "files": {
                "assignment_info": assignment_info_path,
                "rubric_persona": rubric_persona_path,
                "student_work": student_work_path,
            },
            "safe_bundle": safe_bundle_path,
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

    support.write_text(readme_path, "\n".join(readme_lines).rstrip() + "\n")

    return {
        "version": PACKET_VERSION,
        "packet_type": "copilot_batches",
        "mode": "fresh_chat_per_batch",
        "assignment_name": assignment_name,
        "packet_folder": os.path.abspath(bat_container),
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
