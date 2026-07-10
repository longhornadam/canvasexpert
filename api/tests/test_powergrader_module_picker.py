from api.webui.routes.powergrader_setup_support import load_module_picker


def test_module_picker_defaults_to_last_three_modules_and_maps_canvas_items():
    calls = []

    def canvas_get_all(path, params):
        calls.append((path, params))
        if path.endswith("/modules"):
            return [
                {"id": 10, "name": "Orientation"},
                {"id": 20, "name": "Module 1"},
                {"id": 30, "name": "Module 2"},
                {"id": 40, "name": "Module 3"},
            ], None
        module_id = path.split("/modules/")[1].split("/")[0]
        return [
            {"type": "Assignment", "content_id": f"assignment-{module_id}"},
            {"type": "Quiz", "content_id": f"quiz-{module_id}"},
            {"type": "Page", "content_id": f"page-{module_id}"},
        ], None

    payload = load_module_picker("course-1", "", canvas_get_all=canvas_get_all)

    assert payload["ok"] is True
    assert [module["id"] for module in payload["modules"]] == ["10", "20", "30", "40"]
    assert [module["id"] for module in payload["selected_modules"]] == ["20", "30", "40"]
    assert payload["selected_modules"][0]["assignment_ids"] == ["assignment-20"]
    assert payload["selected_modules"][0]["quiz_ids"] == ["quiz-20"]
    assert all(params == {"per_page": 100} for _, params in calls)


def test_module_picker_loads_one_selected_module_and_rejects_unknown_ids():
    def canvas_get_all(path, params):
        if path.endswith("/modules"):
            return [{"id": 10, "name": "Module 1"}, {"id": 20, "name": "Module 2"}], None
        assert "/modules/10/items" in path
        return [{"type": "Assignment", "content_id": 101}], None

    selected = load_module_picker("course-1", "10", canvas_get_all=canvas_get_all)
    missing = load_module_picker("course-1", "999", canvas_get_all=canvas_get_all)

    assert selected["ok"] is True
    assert selected["selected_modules"] == [{
        "id": "10",
        "name": "Module 1",
        "assignment_ids": ["101"],
        "quiz_ids": [],
    }]
    assert missing == {"ok": False, "error": "Selected module is no longer available."}
