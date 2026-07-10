"""Setup-focused support helpers for PowerGrader routes."""


def load_module_picker(course_id: str, module_id: str, *, canvas_get_all) -> dict:
    """Load course modules and the assignment references for the active selection."""
    rows, error = canvas_get_all(
        f"/api/v1/courses/{course_id}/modules",
        {"per_page": 100},
    )
    if error:
        return {"ok": False, "error": error}

    modules = [
        {
            "id": str(row["id"]),
            "name": str(row.get("name") or "Untitled module"),
        }
        for row in (rows or [])
        if isinstance(row, dict) and row.get("id") is not None
    ]

    if module_id:
        selected = [module for module in modules if module["id"] == str(module_id)]
        if not selected:
            return {"ok": False, "error": "Selected module is no longer available."}
    else:
        selected = modules[-3:]

    selected_modules = []
    for module in selected:
        items, error = canvas_get_all(
            f"/api/v1/courses/{course_id}/modules/{module['id']}/items",
            {"per_page": 100},
        )
        if error:
            return {"ok": False, "error": error}

        assignment_ids = []
        quiz_ids = []
        for item in items or []:
            if not isinstance(item, dict) or item.get("content_id") is None:
                continue
            content_id = str(item["content_id"])
            item_type = str(item.get("type") or "").lower()
            if item_type == "assignment":
                assignment_ids.append(content_id)
            elif item_type == "quiz":
                quiz_ids.append(content_id)

        selected_modules.append({
            **module,
            "assignment_ids": assignment_ids,
            "quiz_ids": quiz_ids,
        })

    return {
        "ok": True,
        "modules": modules,
        "selected_modules": selected_modules,
    }


def build_setup_page_context(
    *,
    saved_courses: list[dict],
    rubrics: list[str],
    personas: list[dict],
    has_openrouter: bool,
    openrouter_model: str,
    default_openrouter_model: str,
    openrouter_model_presets: list[dict],
    has_workspace: bool,
    rubrics_folder: str,
    ai_ta_folder: str,
    persona_folder: str,
    source_materials_folder: str,
    source_material_files: list[dict],
    source_response_presets: dict,
) -> dict:
    return {
        "nav_section": "grade",
        "saved_courses": saved_courses,
        "rubrics": rubrics,
        "personas": personas,
        "has_openrouter": has_openrouter,
        "openrouter_model": openrouter_model,
        "default_openrouter_model": default_openrouter_model,
        "openrouter_model_presets": openrouter_model_presets,
        "has_workspace": has_workspace,
        "rubrics_folder": rubrics_folder,
        "ai_ta_folder": ai_ta_folder,
        "persona_folder": persona_folder,
        "source_materials_folder": source_materials_folder,
        "source_material_files": source_material_files,
        "source_response_presets": source_response_presets,
    }


def build_queue_page_context(*, session_id: str, session: dict, canvas_base: str, mode_label: str) -> dict:
    return {
        "nav_section": "grade",
        "session_id": session_id,
        "assignment_name": session.get("assignment_name", ""),
        "course_id": session.get("course_id", ""),
        "mode": session.get("mode", "fast"),
        "mode_label": session.get("mode_label") or mode_label,
        "student_count": len(session.get("students", [])),
        "canvas_base": canvas_base,
    }


def build_estimate_payload(
    *,
    assignment_name: str,
    student_count: int,
    count_basis: str,
    response_kind: str,
    response_label: str,
    source_tokens: int,
    assignment_tokens: int,
    rubric_tokens: int,
    response_tokens_each: int,
    budget: dict,
    materials: list[dict],
    estimated_cost_label: str,
    warnings: list[str],
) -> dict:
    return {
        "ok": True,
        "assignment_name": assignment_name,
        "student_count": student_count,
        "count_basis": count_basis,
        "response_kind": response_kind,
        "response_label": response_label,
        "tokens": {
            "source_materials": source_tokens,
            "assignment_context": assignment_tokens,
            "rubric": rubric_tokens,
            "student_response_each": response_tokens_each,
            "estimated_input": budget.get("input_tokens"),
            "estimated_output": budget.get("estimated_output_tokens"),
        },
        "materials": [
            {
                "title": material.get("title"),
                "source": material.get("source"),
                "tokens_est": material.get("tokens_est"),
                "chars": material.get("chars"),
            }
            for material in materials
        ],
        "budget": budget,
        "estimated_cost_label": estimated_cost_label,
        "warnings": warnings,
        "caching_note": (
            "Estimate assumes fresh input. Some OpenRouter providers may discount "
            "cached prompt reads, but Canvas Expert does not count on that."
        ),
    }
