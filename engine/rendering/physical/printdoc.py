"""Intermediate content model for printable documents.

Slice 1 keeps this intentionally quiz-shaped while separating layout from the
legacy DOCX packager. Later slices can add more block/payload types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias


@dataclass
class PrintDoc:
    title: str
    instructions: str
    blocks: list["Block"] = field(default_factory=list)
    answer_key: "AnswerKey | None" = None


@dataclass
class Stimulus:
    title: str
    author: str
    fmt: str
    body_html: str


@dataclass
class Question:
    number: int
    qtype: str
    prompt_html: str
    payload: "QPayload"


@dataclass
class Choice:
    letter: str
    html: str


@dataclass
class MCPayload:
    choices: list[Choice]
    two_column: bool


@dataclass
class TFPayload:
    pass


@dataclass
class Pair:
    prompt: str
    answer: str


@dataclass
class MatchingPayload:
    pairs: list[Pair]


@dataclass
class OrderingPayload:
    items: list[str]


@dataclass
class CategorizationPayload:
    categories: list[str]
    items: list[str]


@dataclass
class FITBPayload:
    pass


@dataclass
class AnswerLinePayload:
    show_line: bool = True


@dataclass
class EmptyPayload:
    pass


QPayload: TypeAlias = (
    MCPayload
    | TFPayload
    | MatchingPayload
    | OrderingPayload
    | CategorizationPayload
    | FITBPayload
    | AnswerLinePayload
    | EmptyPayload
)

Block: TypeAlias = Stimulus | Question


@dataclass
class KeyRow:
    number: int
    answer: str
    points: str


@dataclass
class AnswerKey:
    rows: list[KeyRow]
    total: str
