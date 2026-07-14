"""PowerGrader start-workflow helpers shared by route orchestration."""


def build_extra_time_map(extra_time_list: list[dict]) -> dict:
    return {str(entry["id"]): entry.get("days", 0) for entry in extra_time_list}


def append_privacy_audit_step(
    *,
    privacy_artifacts: dict,
    assignment_name: str,
    session_id: str,
    course_id: str,
    assignment_id: str,
    mode: str,
    selected_model: str,
    privacy_steps: list[dict],
    write_privacy_audit_file,
    privacy_step,
) -> tuple[dict, list[dict]]:
    if not privacy_artifacts.get("private_folder"):
        return privacy_artifacts, privacy_steps

    audit_path = write_privacy_audit_file(
        privacy_artifacts["private_folder"],
        assignment_name,
        session_id,
        course_id,
        assignment_id,
        selected_model if mode == "assisted" else "",
        privacy_steps,
        privacy_artifacts,
    )
    if audit_path:
        privacy_artifacts["privacy_audit"] = audit_path
        privacy_steps.append(privacy_step(
            "privacy_audit", "Saved PowerGrader privacy audit", "ok",
            "Private decoder folder includes a JSON record of these privacy steps.",
            path=audit_path,
        ))
    else:
        privacy_steps.append(privacy_step(
            "privacy_audit", "Saved PowerGrader privacy audit", "warn",
            "Could not write the optional privacy audit JSON; session still records these steps.",
        ))
    return privacy_artifacts, privacy_steps


def build_start_session(
    *,
    build_session,
    session_id: str,
    course_id: str,
    assignment_id: str,
    assignment_name: str,
    points_possible: float,
    mode: str,
    rubric_name: str,
    persona_id: str,
    selected_model: str,
    assignment_description: str,
    response_kind: str,
    privacy_steps: list[dict],
    privacy_artifacts: dict,
    students: list[dict],
    mode_label: str,
    copilot_packet: dict | None,
    late_watch: dict,
    canvas_writeback_supported: bool = True,
) -> dict:
    return build_session(
        session_id=session_id,
        course_id=course_id,
        assignment_id=assignment_id,
        assignment_name=assignment_name,
        points_possible=points_possible,
        mode=mode,
        rubric_name=rubric_name,
        persona_id=persona_id,
        selected_model=selected_model,
        assignment_description=assignment_description,
        response_kind=response_kind,
        privacy_steps=privacy_steps,
        privacy_artifacts=privacy_artifacts,
        students=students,
        mode_label=mode_label,
        copilot_packet=copilot_packet,
        late_watch=late_watch,
        canvas_writeback_supported=canvas_writeback_supported,
    )
