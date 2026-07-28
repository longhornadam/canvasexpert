"""Single source for the student-facing system name.

The name is not decided yet. Candidates under consideration: WriteReps,
Stacks, Positions. Change the one constant below and every surface follows.

Do not use "Forge": that word already names Canvas Expert's authoring content
kinds (RubricForge and siblings), and a collision would corrupt the docs.

Not to be confused with `api.webui.workspace.SYSTEM_NAME`, which is the name
of the workspace's `_System` folder and has nothing to do with this.
"""
from __future__ import annotations

# Placeholder until the teacher picks one. Referenced only through this
# constant, never spelled out elsewhere in the package.
SYSTEM_NAME = "Daily Writing"

# The unit a student produces in one class day, used in student-facing copy.
REP_NOUN = "rep"
REP_NOUN_PLURAL = "reps"
