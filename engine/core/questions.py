"""Question type domain models.

All question types inherit from the base Question class.
Each type adds specific fields needed for rendering and validation.

Supported types:
- MCQuestion: Multiple choice (select one)
- TFQuestion: True/False
- MAQuestion: Multiple answers (select all that apply)
- NumericalQuestion: Numeric answer with tolerance/precision
- EssayQuestion: Free-form text response
- FileUploadQuestion: File submission
- MatchingQuestion: Match terms to definitions
- FITBQuestion: Fill in the blank
- OrderingQuestion: Arrange items in sequence
- CategorizationQuestion: Sort items into categories
- StimulusItem: 0-point content block for grouping questions
- StimulusEnd: Marker for end of stimulus group
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
from .answers import NumericalAnswer


@dataclass
class Question:
    """Base class for all question types.
    
    Attributes:
        qtype: Question type identifier (MC, TF, MA, NUMERICAL, etc.)
        prompt: Question text shown to student
        render_mode: How student-visible strings are treated during rendering.
            - verbatim (default): never interpret escape sequences like \\n or \\t
            - executable: escape sequences may be interpreted (NOT safe for string-reasoning)
        points: Point value for this question
        points_set: True if points were explicitly set in input file
        parent_stimulus_ident: If set, this question follows a stimulus
        forced_ident: Override default ID generation (used for stimuli)
    """
    qtype: str
    prompt: str
    render_mode: str = "executable"
    points: float = 10.0
    points_set: bool = False
    parent_stimulus_ident: Optional[str] = None
    forced_ident: Optional[str] = None


@dataclass
class MCChoice:
    """A single choice option in a multiple-choice or multiple-answer question.
    
    Attributes:
        text: Display text for this choice
        correct: True if this is a correct answer
    """
    text: str
    correct: bool = False


@dataclass
class MCQuestion(Question):
    """Multiple choice question: select one correct answer from 2-7 choices.
    
    Attributes:
        choices: List of 2-7 choice options (exactly one must be correct)
    """
    choices: List[MCChoice] = field(default_factory=list)


@dataclass
class TFQuestion(Question):
    """True/False question: student selects true or false.
    
    Attributes:
        answer_true: True if correct answer is True, False if correct answer is False
    """
    answer_true: bool = True


@dataclass
class MAQuestion(Question):
    """Multiple answers question: select all correct answers (select all that apply).
    
    Attributes:
        choices: List of choices (one or more must be correct)
    """
    choices: List[MCChoice] = field(default_factory=list)


@dataclass
class EssayQuestion(Question):
    """Essay question: student types free-form response (manual grading required)."""
    pass


@dataclass
class FileUploadQuestion(Question):
    """File upload question: student uploads an artifact (manual grading required)."""
    pass


@dataclass
class MatchingPair:
    """A single prompt-answer pair in a matching question.
    
    Attributes:
        prompt: Left-side term (e.g., vocabulary word)
        answer: Right-side match (e.g., definition)
    """
    prompt: str
    answer: str


@dataclass
class MatchingQuestion(Question):
    """Matching question: student pairs prompts with answers (e.g., term with definition).
    
    Attributes:
        pairs: List of prompt-answer pairs (minimum 2)
    """
    pairs: List[MatchingPair] = field(default_factory=list)


@dataclass
class FITBQuestion(Question):
    """Fill-in-the-blank question: student types text to complete a sentence.
    
    Uses case-insensitive matching. Multiple acceptable answers supported.
    
    Attributes:
        variants: List of acceptable answers (e.g., ["photosynthesis", "Photo synthesis"])
        blank_token: UUID token for identifying the blank in Canvas
        answer_mode: "open_entry" (default), "dropdown", or "wordbank"
        options: Answer options for dropdown/wordbank modes (includes the correct answer)
        variants_per_blank: Accept lists per blank for multi-blank questions
        blank_tokens: Token list (one per blank) for multi-blank questions
    """
    variants: List[str] = field(default_factory=list)
    blank_token: Optional[str] = None
    answer_mode: str = "open_entry"
    options: List[str] = field(default_factory=list)
    variants_per_blank: List[List[str]] = field(default_factory=list)
    blank_tokens: List[str] = field(default_factory=list)


@dataclass
class OrderingItem:
    """A single item in an ordering (sequencing) question.
    
    Attributes:
        text: Display text for this item
        ident: Unique identifier for this item
    """
    text: str
    ident: str


@dataclass
class OrderingQuestion(Question):
    """Ordering question: student arranges items in the correct sequence.
    
    Attributes:
        items: List of items in correct order (minimum 2)
        header: Optional instruction text shown above items
    """
    items: List[OrderingItem] = field(default_factory=list)
    header: Optional[str] = None


@dataclass
class CategoryMapping:
    """Maps an item to its correct category in a categorization question.
    
    Attributes:
        item_text: Display text for the item
        item_ident: Unique identifier for the item
        category_name: Name of the category this item belongs to
    """
    item_text: str
    item_ident: str
    category_name: str


@dataclass
class CategorizationQuestion(Question):
    """Categorization question: student sorts items into named categories.
    
    Partial credit awarded per category.
    
    Attributes:
        categories: List of category names (minimum 2)
        category_idents: Dict mapping category name to UUID
        items: List of items and their correct categories
        distractors: List of items that don't belong in any category
        distractor_idents: Dict mapping distractor text to UUID
    """
    categories: List[str] = field(default_factory=list)
    category_idents: dict = field(default_factory=dict)
    items: List[CategoryMapping] = field(default_factory=list)
    distractors: List[str] = field(default_factory=list)
    distractor_idents: dict = field(default_factory=dict)


@dataclass
class NumericalQuestion(Question):
    """Numerical question: student enters a number, graded with tolerance/precision/range.
    
    Attributes:
        answer: NumericalAnswer specification with tolerance/precision/range settings
    """
    answer: NumericalAnswer = field(default_factory=NumericalAnswer)
    
    def validate(self) -> List[str]:
        """Validate numerical answer specification.
        
        Returns:
            List of error messages (delegates to NumericalAnswer.validate())
        """
        return self.answer.validate()


@dataclass
class StimulusItem(Question):
    """Stimulus content block (0 points): visual prompt that precedes and groups related questions.
    
    Used for reading passages, images, data tables, etc. that multiple questions reference.
    """
    layout: str = "below"
    title: str = ""
    author: str = ""


@dataclass
class StimulusEnd(Question):
    """Sentinel marker: signals the end of a stimulus group. Not rendered as a question."""
    pass
