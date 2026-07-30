Glass contracts
===============

Glass has two agent-authored artifacts. Use `Glass Pane contract.txt` to create a reusable
pane package and `Glass Scene contract.txt` to arrange approved pane revisions on a date.
Assistants write only pending drafts in `To Review/Glass`; teachers preview and approve them
in the local app. Approval creates immutable pane revisions under `Library/Glass/panes` and
atomically replaces the one approved scene for a date under `Library/Glass/scenes`.

Bell schedules remain top-level `canvasexpert.bell_schedule/1` JSON files in this folder.
They are the source of valid block ids and current-block timing; they never contain student
data. Academic-calendar events come only from selected imported calendars.

Pane source executes in an opaque-origin, no-network iframe. Do not use external URLs,
network APIs, student data, Canvas data, or private paths. Preview helps find mistakes but
cannot make arbitrary approved JavaScript free of CPU-exhaustion risk.
