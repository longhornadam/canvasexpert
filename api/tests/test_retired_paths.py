"""Guard the repository's deliberate removals against accidental resurrection."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

# Keep the reason beside each path.  A failure should tell the next maintainer
# which historical decision they are about to undo.
RETIRED_PATHS = (
    ("CLAUDE.md", "bfe1877", "Add TAForge and canonical agent guidance"),
    (
        "api/default_docs/AI Authoring/NoteForge_Base.md",
        "(none)",
        "old-lineage only; NoteForge leaves no other trace on this lineage",
    ),
    ("api/downloader.py", "f8a8f22", "Retire duplicate Download Work workflow"),
    ("api/tests/test_downloader.py", "f8a8f22", "Retire duplicate Download Work workflow"),
    ("api/tests/test_noteforge_physical_routes.py", "926b4f2", "Modularize live-fire workflows"),
    ("api/webui/activity.py", "6110c48", "Complete 0.75beta local hardening and MCP support"),
    ("api/webui/config.py", "87b2a80", "Refactor web UI modules and document next slices"),
    ("api/webui/push_service.py", "cbd6738", "Cleanup legacy Course Expert standalone push surfaces"),
    ("api/webui/static/style.css", "1c2d9f7", "Complete WebUI presentation migration"),
    ("api/webui/templates/_course_picker.html", "1c2d9f7", "Complete WebUI presentation migration"),
    ("api/webui/templates/download_work.html", "cbd6738", "Cleanup legacy Course Expert standalone push surfaces"),
    ("api/webui/templates/feedback_expert.html", "f53394e", "Complete local-first Luna 5-7 surfaces"),
    ("api/webui/templates/name_manager.html", "1c2d9f7", "Complete WebUI presentation migration"),
    ("api/webui/templates/push_assignment.html", "cbd6738", "Cleanup legacy Course Expert standalone push surfaces"),
    ("api/webui/templates/push_note.html", "926b4f2", "Modularize live-fire workflows"),
    ("api/webui/templates/push_page.html", "cbd6738", "Cleanup legacy Course Expert standalone push surfaces"),
    ("api/webui/templates/push_quick.html", "cbd6738", "Cleanup legacy Course Expert standalone push surfaces"),
    ("api/webui/templates/push_quiz.html", "cbd6738", "Cleanup legacy Course Expert standalone push surfaces"),
    ("api/webui/templates/push_rubric.html", "cbd6738", "Cleanup legacy Course Expert standalone push surfaces"),
    ("api/default_docs/AI Authoring/Author a SmartDeck (SlideForge).txt", "(none)", "Retire the classroom-display authoring contract"),
    ("api/default_docs/SmartDecks/Teacher Schedule.template.json", "(none)", "Move the teacher schedule seed into Calendars"),
    ("api/smartdeck_feeds.py", "(none)", "Retire dead classroom-display feed projections"),
    ("api/tests/test_smartdeck_routes.py", "(none)", "Retire the classroom-display management routes"),
    ("api/tests/test_smartdeck_display.py", "(none)", "Retire the classroom-display projector routes"),
    ("api/tests/test_smartdeck_feeds.py", "(none)", "Retire dead classroom-display feed tests"),
    ("api/tests/test_deck_store.py", "(none)", "Retire classroom-display storage"),
    ("api/tests/test_sf.py", "(none)", "Retire the classroom-display format validator"),
    ("api/webui/routes/smartdeck.py", "(none)", "Retire the classroom-display routes"),
    ("api/webui/deck_store.py", "(none)", "Retire classroom-display storage"),
    ("api/webui/sf.py", "(none)", "Retire the classroom-display format validator"),
    ("api/webui/templates/smartdeck.html", "(none)", "Retire the classroom-display management UI"),
    ("api/webui/templates/smartdeck_display.html", "(none)", "Retire the classroom-display projector UI"),
    ("api/webui/static/smartdeck/smartdeck.js", "(none)", "Retire the classroom-display management UI"),
    ("api/webui/static/smartdeck/smartdeck.css", "(none)", "Retire the classroom-display management UI"),
    ("api/webui/static/smartdeck/slide_select.js", "(none)", "Retire the classroom-display projector UI"),
    ("api/webui/static/smartdeck/display.js", "(none)", "Retire the classroom-display projector UI"),
    ("api/webui/static/smartdeck/display.css", "(none)", "Retire the classroom-display projector UI"),
    ("api/tests/smartdeck/widget_lifecycle.test.mjs", "(none)", "Retire classroom-display browser tests"),
    ("api/tests/smartdeck/test_display_js.py", "(none)", "Retire classroom-display browser tests"),
    ("api/tests/smartdeck/slide_select.test.mjs", "(none)", "Retire classroom-display browser tests"),
    ("docs/reference/smartdeck-module-map.md", "(none)", "Retire the classroom-display route card"),
    ("api/webui/deck_schedule.py", "(none)", "Rename the schedule resolver to day_schedule"),
    ("api/tests/test_deck_schedule.py", "(none)", "Rename the schedule resolver tests to day_schedule"),
    ("docs/handoffs/smartdeck-slice1-schedules.md", "(none)", "old-lineage only; completed slice handoff"),
    ("docs/handoffs/smartdeck-slice2-contract-and-writes.md", "(none)", "old-lineage only; completed slice handoff"),
    ("docs/handoffs/smartdeck-slice3-management-ui.md", "(none)", "old-lineage only; completed slice handoff"),
    ("docs/handoffs/smartdeck-slice4-display-and-timer.md", "(none)", "old-lineage only; completed slice handoff"),
    ("engine/dev/test_cases/test_orchestrator_manual.py", "(none)", "orphaned by a405b24; imported the retired engine.orchestrator"),
    ("engine/orchestrator.py", "a405b24", "cruft-removal audit: retire dead code"),
    ("engine/packagers/note_handler.py", "926b4f2", "Modularize live-fire workflows"),
    ("engine/rendering/physical/note_adapter.py", "926b4f2", "Modularize live-fire workflows"),
    ("engine/rendering/physical/note_spike.py", "926b4f2", "Modularize live-fire workflows"),
    ("engine/rendering/physical/templates/note.html.j2", "926b4f2", "Modularize live-fire workflows"),
    ("engine/tests/integration/test_backwards_compatibility.py", "a405b24", "cruft-removal audit: retire dead code"),
    ("engine/tests/integration/test_orchestrator.py", "a405b24", "cruft-removal audit: retire dead code"),
    ("engine/tests/unit/test_noteforge_cornell.py", "926b4f2", "Modularize live-fire workflows"),
    ("engine/tests/unit/test_noteforge_frayer.py", "926b4f2", "Modularize live-fire workflows"),
    ("engine/tests/unit/test_noteforge_guided_cloze.py", "926b4f2", "Modularize live-fire workflows"),
    ("engine/tests/unit/test_noteforge_live_handler.py", "926b4f2", "Modularize live-fire workflows"),
)


def test_retired_paths_are_absent():
    present = []
    for relative, retired_by, subject in RETIRED_PATHS:
        if (REPO_ROOT / relative).exists():
            origin = (
                f"retired by {retired_by}"
                if retired_by != "(none)"
                else "old-lineage only (no retirement commit)"
            )
            present.append(f"{relative}: present; {origin}; {subject}")

    assert not present, "Retired path resurrection detected:\n" + "\n".join(present)
