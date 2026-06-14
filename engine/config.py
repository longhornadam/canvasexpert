"""Engine configuration flags."""

import os

# Switch between legacy text spec and new JSON spec.
# "json" - JSON 3.0 pipeline (default; requires QUIZFORGE_JSON tags).
# "text" - legacy text spec (for backward compatibility).
SPEC_MODE = os.getenv("QUIZFORGE_SPEC_MODE", "json")

