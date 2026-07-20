"""Default styling for physical quizzes.

DOCX-specific styling constants for consistent formatting across all physical outputs.
"""

# DOCX Font Settings
DOCX_FONT_FAMILY = 'Calibri'
DOCX_TITLE_SIZE = 16  # points
DOCX_HEADING_SIZE = 12  # points
DOCX_BODY_SIZE = 11  # points
DOCX_SMALL_SIZE = 9  # points (for answer keys)

# DOCX Margins (in inches)
DOCX_MARGIN_TOP = 0.75
DOCX_MARGIN_BOTTOM = 0.75
DOCX_MARGIN_LEFT = 0.75
DOCX_MARGIN_RIGHT = 0.75

# DOCX Spacing
DOCX_PARA_SPACING_BEFORE = 6  # points
DOCX_PARA_SPACING_AFTER = 6  # points
DOCX_LINE_SPACING = 1.15  # multiple
DOCX_QUESTION_SPACING = 12  # points between questions

# Layout Decision Thresholds
MC_TWO_COLUMN_THRESHOLD = 50  # chars - use 2 columns if all choices under this
MC_CHOICE_MAX_LENGTH = 200  # chars - warn if choice exceeds
STIMULUS_MIN_LENGTH = 100  # chars - treat as passage if over this

# Answer Key Table Settings
TABLE_HEADER_BOLD = True
TABLE_GRID_LINES = True
TABLE_COL_WIDTHS = {
    'question_num': 1.0,  # inches
    'correct_answer': 3.0,
    'points': 1.0
}

# Validation Logging
LOG_ANSWER_CHOICE_STATS = True
LOG_QUESTION_LENGTH_STATS = True
LOG_POINT_VALUE_DISTRIBUTION = True
LOG_STIMULUS_USAGE = True

# Point Calculation Settings
DEFAULT_QUIZ_POINTS = 100
HEAVY_QUESTION_WEIGHT = 2.5  # Multiplier for ESSAY and FILEUPLOAD
HEAVY_QUESTION_TYPES = ['ESSAY', 'FILEUPLOAD']