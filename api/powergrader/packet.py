"""Safe AI Packet building helpers for PowerGrader.

Creates the teacher-facing packet folder and ZIP from SAFE artifacts,
including student responses, source materials, rubric instructions, and
paste-back JSON format.
"""

import json
import os
import zipfile

from api import feedback_artifacts, feedback_contract
from api import feedback_pipeline as fp
from api.platform_services import workspace
from . import scoring_packet


def _assignment_stable_id(assignment_name: str, assignment_id: str = "") -> str:
    """Return a deterministic stable identifier for an assignment.

    Prefers the Canvas assignment ID; falls back to a deterministic short
    hash of the assignment name so two names produce distinct IDs.
    """
    if assignment_id:
        return workspace.safe_id(assignment_id)
    return workspace._deterministic_hash(assignment_name)


def safe_ai_packet_name(assignment_name: str, *, assignment_id: str = "", compact: bool = False) -> str:
    if compact:
        stable = _assignment_stable_id(assignment_name, assignment_id)
        return f"Packet-{stable}"
    return f"Safe AI Packet - {fp.safe(assignment_name, max_len=60)}"


def packet_paths(safe_dir: str, assignment_name: str, *, assignment_id: str = "",
                 compact: bool = False, reserve: int = 0) -> dict:
    packet_name = safe_ai_packet_name(assignment_name, assignment_id=assignment_id, compact=compact)
    pdir = os.path.join(safe_dir, packet_name)
    pzip = os.path.join(safe_dir, f"{packet_name}.zip")
    # When reserve is given, use the teacher_visible_path helper to ensure
    # the deepest projected child still fits the budget.
    if reserve:
        base_dir = safe_dir
        # Project the deepest expected child: batch index "99", file "03-work.md"
        deepest_child = f"Batches{os.sep}Batch-99{os.sep}03-work.md"
        deep_full = os.path.join(base_dir, packet_name, deepest_child)
        deep_len = len(deep_full)
        if deep_len > workspace.TEACHER_VISIBLE_BUDGET - reserve:
            return {"name": packet_name, "dir": pdir, "zip": pzip}
            # Return as-is; the caller will get the budget exception from
            # the deeper validation or switch to compact mode.
    return {
        "name": packet_name,
        "dir": pdir,
        "zip": pzip,
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
            oral_text = feedback_artifacts.oral_reading_text(response.get("oral_reading"))
            if oral_text:
                lines.extend(["", oral_text])
            lines.append("")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def paste_format_text(bundle: dict, persona: dict | None = None, *, packet_digest: str = "") -> str:
    first_student = ((bundle or {}).get("students") or [{}])[0]
    first_response = ((first_student.get("responses") or [{}])[0])
    pseudonym = first_student.get("pseudonym") or "<copy pseudonym exactly>"
    item_id = first_response.get("item_id") or "<copy item_id exactly>"
    contract = feedback_contract.scoring_output_contract(
        persona=persona,
        identity_source="Student Responses.json",
        pseudonym=pseudonym,
        item_id=str(item_id),
        include_signoff_in_feedback=True,
        packet_digest=packet_digest if feedback_artifacts.has_oral_reading(bundle) else "",
    )
    return (
        "Paste Results Back Here - Format\n"
        "================================\n\n"
        "After your AI chat scores the packet, paste ONLY the JSON array or a JSON "
        "object with a results array back into PowerGrader.\n\n"
        "Required shape:\n\n"
        + json.dumps(contract["envelope"] or [contract["sample"]], indent=2, ensure_ascii=False)
        + "\n\nRules:\n"
        + contract["rules_text"]
        + "\n"
        "- PowerGrader validates this before adding AI suggestions to the session.\n"
    )


def build_safe_ai_packet(
    assignment_name: str,
    safe_dir: str,
    write_result: dict,
    llm_bundle: dict,
    persona: dict | None = None,
    assignment_id: str = "",
    session_id: str = "",
) -> dict:
    """Create a teacher-facing packet folder + ZIP from the SAFE artifacts.

    Selects the normal (readable) or compact layout based on whether the
    projected paths fit within the teacher-visible 230-character budget.
    All returned metadata paths are plain (unprefixed) and at most 230 chars.
    """
    # Determine whether the deep workspace forces compact layout: project the
    # readable packet name plus its deepest expected child (the bundle JSON).
    # If even compact doesn't fit, _validate_packet_budget raises below.
    readable_name = safe_ai_packet_name(assignment_name, assignment_id=assignment_id)
    compact = workspace.needs_compact_layout(
        safe_dir, readable_name, longest_packet_child(write_result))

    paths = packet_paths(safe_dir, assignment_name, assignment_id=assignment_id, compact=compact)
    packet_dir = paths["dir"]

    # Validate every child path against the budget before creating anything.
    _validate_packet_budget(packet_dir, write_result)

    os.makedirs(workspace.extended_path(packet_dir), exist_ok=True)

    files: list[str] = []

    def write_packet_file(name: str, text: str):
        path = os.path.join(packet_dir, name)
        with open(workspace.extended_path(path), "w", encoding="utf-8") as f:
            f.write(text)
        files.append(path)

    how_to_path = write_result.get("how_to_score")
    if how_to_path and os.path.isfile(workspace.extended_path(how_to_path)):
        with open(workspace.extended_path(how_to_path), encoding="utf-8") as f:
            instructions = f.read()
    else:
        instructions = fp.build_contract_text("your teaching assistant", persona=persona)
    write_packet_file("START HERE - Instructions for your AI.txt", instructions)

    bundle_path = os.path.join(packet_dir, "Student Responses.json")
    with open(workspace.extended_path(bundle_path), "w", encoding="utf-8") as f:
        json.dump(llm_bundle, f, indent=2, ensure_ascii=False)
    files.append(bundle_path)

    write_packet_file("Student Responses - readable.txt", readable_responses_text(llm_bundle))

    shared_text = shared_context_text(llm_bundle)
    write_packet_file(
        "Source Materials.txt",
        shared_text or "No separate source material was included in this packet.\n",
    )
    packet_digest = scoring_packet.packet_digest(session_id, llm_bundle)
    write_packet_file(
        "Paste Results Back Here - Format.txt",
        paste_format_text(llm_bundle, persona, packet_digest=packet_digest),
    )

    for student_txt in write_result.get("student_txts") or []:
        if os.path.isfile(workspace.extended_path(student_txt)):
            dest = os.path.join(packet_dir, os.path.basename(student_txt))
            with open(workspace.extended_path(student_txt), "rb") as src, open(workspace.extended_path(dest), "wb") as out:
                out.write(src.read())
            files.append(dest)

    with zipfile.ZipFile(workspace.extended_path(paths["zip"]), "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(workspace.extended_path(path), arcname=os.path.basename(path))

    return {
        "packet_name": paths["name"],
        "packet_folder": packet_dir,
        "packet_zip": paths["zip"],
        "packet_files": files,
        **({"packet_digest": packet_digest} if feedback_artifacts.has_oral_reading(llm_bundle) else {}),
    }


# Every file build_safe_ai_packet writes directly under the packet folder.
# Single source of truth: both the readable-vs-compact probe and the budget
# validator read this, so they cannot disagree about which child is deepest.
# They previously did -- the probe measured "Student Responses.json" (22 chars)
# while the validator checked "START HERE - Instructions for your AI.txt" (41),
# so a packet folder could pass the probe by one character and fail validation
# by eighteen.
PACKET_FIXED_CHILDREN = (
    "START HERE - Instructions for your AI.txt",
    "Student Responses.json",
    "Student Responses - readable.txt",
    "Source Materials.txt",
    "Paste Results Back Here - Format.txt",
)


def packet_child_names(write_result: dict | None = None) -> list[str]:
    """Every file name written directly under the packet folder.

    ``write_result`` adds the per-student files when they are known; the
    preflight runs before they exist and passes nothing.
    """
    children = list(PACKET_FIXED_CHILDREN)
    for student_txt in (write_result or {}).get("student_txts") or []:
        children.append(os.path.basename(student_txt))
    return children


def longest_packet_child(write_result: dict | None = None) -> str:
    """The child name that decides whether the packet folder fits its budget."""
    return max(packet_child_names(write_result), key=len)


def preflight_packet_budget(safe_dir: str, assignment_name: str,
                            assignment_id: str = "") -> str | None:
    """Check the packet folder will fit *before* any artifact is written.

    Returns a teacher-facing message when even the compact layout cannot fit,
    or None when the run may proceed. Callers write nothing until this passes:
    the budget failure used to surface from ``build_safe_ai_packet``, which
    runs after the flat SAFE/PRIVATE artifacts are already on disk, stranding
    them with no registered session.

    Per-student file names do not exist yet, so this measures the fixed
    children -- which is what the readable-vs-compact decision turns on.
    """
    longest = longest_packet_child()
    for compact in (False, True):
        name = safe_ai_packet_name(assignment_name, assignment_id=assignment_id,
                                   compact=compact)
        projected = os.path.join(os.path.abspath(safe_dir), name, longest)
        if len(projected) <= workspace.TEACHER_VISIBLE_BUDGET:
            return None
    return (
        "This assignment's workspace folder is too deeply nested to hold a Safe AI "
        f"Packet: even the shortened folder name projects past the "
        f"{workspace.TEACHER_VISIBLE_BUDGET}-character path limit. Nothing was written. "
        "Move the CanvasExpert workspace closer to the drive root, or shorten the "
        "course or assignment name, then run this again."
    )


def _validate_packet_budget(packet_dir: str, write_result: dict) -> None:
    """Validate every expected packet child path against the budget.

    Raises TeacherVisiblePathBudgetError if any projected path exceeds
    TEACHER_VISIBLE_BUDGET.  This is called *before* any directory or file
    is created by the packet writer.
    """
    for child in packet_child_names(write_result):
        projected = os.path.join(packet_dir, child)
        if len(projected) > workspace.TEACHER_VISIBLE_BUDGET:
            raise workspace.TeacherVisiblePathBudgetError(
                f"Packet child path exceeds budget "
                f"({len(projected)} > {workspace.TEACHER_VISIBLE_BUDGET}): {projected}"
            )

    # ZIP path
    zip_path = packet_dir + ".zip"
    if len(zip_path) > workspace.TEACHER_VISIBLE_BUDGET:
        raise workspace.TeacherVisiblePathBudgetError(
            f"Packet ZIP path exceeds budget "
            f"({len(zip_path)} > {workspace.TEACHER_VISIBLE_BUDGET}): {zip_path}"
        )
