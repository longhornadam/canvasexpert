"""Adapt Quiz domain objects into the print-document model."""

from __future__ import annotations

import html
import re

from engine.core.quiz import Quiz
from engine.core.questions import (
    CategorizationQuestion,
    EssayQuestion,
    FITBQuestion,
    FileUploadQuestion,
    MAQuestion,
    MCQuestion,
    MatchingQuestion,
    NumericalQuestion,
    OrderingQuestion,
    StimulusEnd,
    StimulusItem,
    TFQuestion,
)
from engine.rendering.physical.printdoc import (
    AnswerKey,
    AnswerLinePayload,
    CategorizationPayload,
    Choice,
    EmptyPayload,
    FITBPayload,
    KeyRow,
    MatchingPayload,
    MCPayload,
    Pair,
    PrintDoc,
    Question,
    Stimulus,
    TFPayload,
    OrderingPayload,
)
from engine.rendering.physical.styles.default_styles import MC_TWO_COLUMN_THRESHOLD


def to_printdoc(quiz: Quiz) -> PrintDoc:
    """Build a PrintDoc from a validated Quiz.

    This mirrors the existing physical handler's trust-input contract: no
    validation happens here.
    """

    blocks = []
    question_number = 1

    for group in _group_questions_by_stimulus(quiz.questions):
        if group["stimulus"]:
            fmt = group.get("stimulus_format", "text") or "text"
            raw = group["stimulus"]
            body = _extract_code(raw) if fmt == "code" else _clean_prompt_text(raw)
            blocks.append(
                Stimulus(
                    title=group.get("stimulus_title", ""),
                    author=group.get("stimulus_author", ""),
                    fmt=fmt,
                    body_html=body,
                )
            )

        for question in group["questions"]:
            blocks.append(_question_to_block(question, question_number))
            question_number += 1

    return PrintDoc(
        title=quiz.title,
        instructions=getattr(quiz, "instructions", "") or "",
        blocks=blocks,
        answer_key=_build_answer_key(quiz),
    )


def _question_to_block(question, number: int) -> Question:
    prompt_html = _clean_prompt_text(question.prompt)

    if isinstance(question, FITBQuestion):
        prompt_html = _replace_fitb_tokens(prompt_html, question)
        payload = FITBPayload()
    elif isinstance(question, (MCQuestion, MAQuestion)):
        choices = [
            Choice(letter=chr(65 + idx), html=choice.text)
            for idx, choice in enumerate(question.choices)
        ]
        two_column = all(
            len(_strip_html(choice.text).strip()) < MC_TWO_COLUMN_THRESHOLD
            for choice in question.choices
        )
        payload = MCPayload(choices=choices, two_column=two_column)
    elif isinstance(question, TFQuestion):
        payload = TFPayload()
    elif isinstance(question, MatchingQuestion):
        payload = MatchingPayload(
            pairs=[Pair(prompt=pair.prompt, answer=pair.answer) for pair in question.pairs]
        )
    elif isinstance(question, OrderingQuestion):
        payload = OrderingPayload(
            items=[item.text if hasattr(item, "text") else str(item) for item in question.items]
        )
    elif isinstance(question, CategorizationQuestion):
        items = [
            entry.item_text if hasattr(entry, "item_text") else entry.get("label", "")
            for entry in getattr(question, "items", [])
        ]
        items.extend(str(label) for label in (getattr(question, "distractors", []) or []))
        payload = CategorizationPayload(
            categories=[str(cat) for cat in getattr(question, "categories", [])],
            items=items,
        )
    elif isinstance(question, (NumericalQuestion, EssayQuestion)):
        payload = AnswerLinePayload()
    elif isinstance(question, FileUploadQuestion):
        payload = EmptyPayload()
    else:
        payload = AnswerLinePayload()

    return Question(number=number, qtype=question.qtype, prompt_html=prompt_html, payload=payload)


def _build_answer_key(quiz: Quiz) -> AnswerKey:
    rows = []
    question_number = 1

    for question in quiz.questions:
        if isinstance(question, (StimulusItem, StimulusEnd)):
            continue
        rows.append(
            KeyRow(
                number=question_number,
                answer=_get_correct_answer_text(question),
                points=str(question.points),
            )
        )
        question_number += 1

    return AnswerKey(rows=rows, total=str(quiz.total_points()))


def _replace_fitb_tokens(prompt_html: str, question: FITBQuestion) -> str:
    tokens = list(getattr(question, "blank_tokens", []) or [])
    token = getattr(question, "blank_token", "")
    if token:
        tokens.append(token)

    for token_value in tokens:
        prompt_html = prompt_html.replace(f"[{token_value}]", "__________________")

    return prompt_html.replace("[blank]", "__________________")


def _group_questions_by_stimulus(questions):
    groups = []
    current_stimulus = None
    current_stimulus_format = None
    current_questions = []
    current_stimulus_title = ""
    current_stimulus_author = ""

    for question in questions:
        if isinstance(question, StimulusItem):
            if current_questions:
                groups.append(
                    {
                        "stimulus": current_stimulus,
                        "stimulus_format": current_stimulus_format,
                        "stimulus_title": current_stimulus_title,
                        "stimulus_author": current_stimulus_author,
                        "questions": current_questions,
                    }
                )
            current_stimulus = question.prompt
            current_stimulus_format = _detect_stimulus_format(question.prompt)
            current_stimulus_title = getattr(question, "title", "") or ""
            current_stimulus_author = getattr(question, "author", "") or ""
            current_questions = []
        elif isinstance(question, StimulusEnd):
            if current_questions:
                groups.append(
                    {
                        "stimulus": current_stimulus,
                        "stimulus_format": current_stimulus_format,
                        "stimulus_title": current_stimulus_title,
                        "stimulus_author": current_stimulus_author,
                        "questions": current_questions,
                    }
                )
            current_stimulus = None
            current_stimulus_format = None
            current_stimulus_title = ""
            current_stimulus_author = ""
            current_questions = []
        else:
            current_questions.append(question)

    if current_questions:
        groups.append(
            {
                "stimulus": current_stimulus,
                "stimulus_format": current_stimulus_format,
                "stimulus_title": current_stimulus_title,
                "stimulus_author": current_stimulus_author,
                "questions": current_questions,
            }
        )

    return groups


def _get_correct_answer_text(question) -> str:
    if isinstance(question, MCQuestion):
        for idx, choice in enumerate(question.choices):
            if choice.correct:
                return chr(65 + idx)
        return "?"

    if isinstance(question, TFQuestion):
        return "True" if question.answer_true else "False"

    if isinstance(question, NumericalQuestion):
        return str(question.answer.answer)

    if isinstance(question, MAQuestion):
        correct_letters = [
            chr(65 + idx) for idx, choice in enumerate(question.choices) if choice.correct
        ]
        return ", ".join(correct_letters) if correct_letters else "?"

    if isinstance(question, MatchingQuestion):
        pairs = [f"{pair.prompt} -> {pair.answer}" for pair in question.pairs]
        return "; ".join(pairs) if pairs else "?"

    if isinstance(question, FITBQuestion):
        accepted_answers = getattr(question, "accepted_answers", None)
        if accepted_answers:
            return ", ".join(accepted_answers)

        variants = getattr(question, "variants", []) or []
        per_blank = getattr(question, "variants_per_blank", []) or []

        if per_blank:
            parts = []
            for idx, group in enumerate(per_blank, 1):
                if group:
                    unique = list(dict.fromkeys(str(value) for value in group))
                    parts.append(f"Blank {idx}: " + " | ".join(unique))
            if parts:
                return "; ".join(parts)

        if variants:
            unique = list(dict.fromkeys(str(value) for value in variants))
            return " | ".join(unique)

        return "?"

    if isinstance(question, (EssayQuestion, FileUploadQuestion)):
        return "See rubric"

    return "See rubric"


def _clean_prompt_text(prompt: str) -> str:
    cleaned = re.sub(r"```[a-zA-Z]*", "", prompt or "")
    cleaned = cleaned.replace("```", "")
    return cleaned.strip()


def _detect_stimulus_format(raw_prompt: str) -> str:
    if not raw_prompt:
        return "text"
    if re.search(r"```\s*(poetry|verse)", raw_prompt, re.IGNORECASE):
        return "poetry"
    # Code arrives either as a markdown fence or as authored HTML <pre>/<code>
    # (often with a dark inline background we deliberately discard).
    if "```" in raw_prompt or re.search(r"<\s*(pre|code)\b", raw_prompt, re.IGNORECASE):
        return "code"
    return "text"


def _extract_code(raw_prompt: str) -> str:
    """Pull the code body out, preserving indentation and line breaks and
    dropping all author markup/inline styles (so a dark code theme can never
    bleed into print).

    Handles both the markdown fence form and the HTML <pre>/<code> form.
    """
    raw = raw_prompt or ""

    fence = re.search(r"```[a-zA-Z0-9_+-]*[ \t]*\r?\n?(.*?)```", raw, re.DOTALL)
    if fence:
        return fence.group(1).strip("\r\n")

    inner = re.search(r"<code[^>]*>(.*?)</code>", raw, re.DOTALL | re.IGNORECASE) or re.search(
        r"<pre[^>]*>(.*?)</pre>", raw, re.DOTALL | re.IGNORECASE
    )
    text = inner.group(1) if inner else raw
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip("\r\n")


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "")
