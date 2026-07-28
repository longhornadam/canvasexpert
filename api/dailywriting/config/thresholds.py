"""Tunable thresholds. Every magic number in the package lives here.

Values are starting points chosen to be defensible, not calibrated. The
monthly blind-calibration sample in `core.digest` is what turns them from
guesses into measurements, so expect to move them once real agreement
numbers exist.
"""
from __future__ import annotations

# --- Segmentation -----------------------------------------------------------

# Token-sequence similarity above which a window counts as a reworded copy of
# provided text (prompt, scaffold, boilerplate).
FUZZY_MATCH_THRESHOLD = 0.85

# Quoting the passage is the assignment from tier 3 on, so source matching is
# held to a stricter bar than prompt restatement.
QUOTED_SOURCE_THRESHOLD = 0.90

# A stem literal shorter than this carries too little signal to align on.
STEM_MIN_LITERAL_TOKENS = 2

# Shortest run of submission words that counts as a quotation lifted out of a
# longer source passage. Below this, common phrasing produces false quotes.
EMBEDDED_QUOTE_MIN_TOKENS = 5

# Mid-prompt fragment detection only runs on a response at least this long.
# The fixture corpus's longest single response is 74 tokens and every daily
# rep sits well under 100; extended writing, the case that stage exists for,
# runs 400-1500 words. A handful of verbatim prompt words is structurally
# different depending on which side of that gap they land on: near the top of
# a 20-40 word rep they are usually most of the response's own thesis
# (measured: fixture 2's 12-word answer lost 10 of them, fixture 6's strong
# 38-word answer lost 5), which is either genuine prompt-restatement --
# already the job of `observations.py`'s `restates_prompt` tag -- or simply
# the student answering the question in the question's own words, not
# evidence of copying. Three paragraphs into a several-hundred-word piece the
# same five words are a rounding error, and nothing shorter is watching for
# them. 150 sits with a wide margin on both sides rather than pinned to
# either edge.
MID_PROMPT_FRAGMENT_MIN_RESPONSE_TOKENS = 150

# Cross-submission repetition: identical residual text appearing in this many
# students' work on the same rep is probably provided text the authoring
# record missed. Flags for human eyes; never changes a segment's origin.
CROSS_SUBMISSION_REPEAT_MIN_STUDENTS = 3
CROSS_SUBMISSION_REPEAT_MIN_TOKENS = 6

# Below this, a segment origin is reported as low confidence and surfaced to
# the teacher digest rather than trusted.
LOW_CONFIDENCE_SEGMENT = 0.90

# --- Scoring ----------------------------------------------------------------

# Content-word overlap with the prompt above which a "thesis" is a
# restatement rather than a position.
RESTATEMENT_OVERLAP = 0.70

# Overlap floor for "this text engages the prompt at all".
ANSWERS_PROMPT_OVERLAP = 0.20

# Overlap floor for argument/evidence/commentary tying back to the thesis.
ON_THESIS_OVERLAP = 0.15

# Above this, commentary is restating its evidence instead of interpreting it.
COMMENTARY_RESTATEMENT_OVERLAP = 0.60

# A thesis shorter than this is too thin to be specific.
SPECIFIC_MIN_WORDS = 8

# --- Directives and uptake --------------------------------------------------

# Consecutive met evaluations before an uptake acknowledgment fires.
PRAISE_THRESHOLD = 3

# Consecutive met evaluations before a directive retires and stops appearing
# in feedback. The file should not nag forever.
RETIRE_THRESHOLD = 6

# A directive only "lapses" if it had earned a real streak first.
LAPSE_MIN_BEST_STREAK = 3

# --- Rolling profile --------------------------------------------------------

PROFILE_WINDOW_WEEKS = 4
PROFILE_MAX_ACTIVE_PATTERNS = 4

# Occurrences before a pattern is worth steering feedback with. 1 means a
# single dated noticing counts; raise it to 2 to suppress one-offs once there
# is enough history for that to be a real signal rather than silence.
PROFILE_MIN_PATTERN_COUNT = 1

# Tier-advance recommendation. Recommendation only: the teacher advances.
TIER_ADVANCE_RATE = 0.80
TIER_ADVANCE_MIN_SUBMISSIONS = 6

# --- Feedback ---------------------------------------------------------------

# A 12-year-old reads about this much feedback, not four hundred words.
FEEDBACK_WORD_CAP = 120

# Latency that makes the practice feel consequential. Monitored, not hoped for.
FEEDBACK_LATENCY_HOURS = 24

# --- Digest -----------------------------------------------------------------

DIGEST_TOP_PATTERNS = 5
DIGEST_SPANS_PER_PATTERN = 3
CALIBRATION_SAMPLE_SIZE = 20
CALIBRATION_STRATA = 4
