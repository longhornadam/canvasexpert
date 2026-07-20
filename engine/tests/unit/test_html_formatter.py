import xml.etree.ElementTree as ET

from engine.core.questions import MCChoice, MCQuestion
from engine.core.quiz import Quiz
from engine.rendering.canvas.html_formatter import (
    add_passage_numbering,
    apply_syntax_highlighting_to_html,
    htmlize_choice,
    htmlize_item_text,
    htmlize_prompt,
    plaintext_item_text,
    transform_code_blocks,
)
from engine.rendering.canvas.qti_builder import build_assessment_xml


def test_verbatim_mode_preserves_formatter_inputs_exactly():
    text = "Line one\\nLine two with `x < y`.\n```python\nprint(1)\n```"

    assert htmlize_prompt(text, render_mode="verbatim") == text
    assert htmlize_choice(text, render_mode="verbatim") == text
    assert htmlize_item_text(text, render_mode="verbatim") == text
    assert plaintext_item_text(text, render_mode="verbatim") == text
    assert transform_code_blocks(text, render_mode="verbatim") == text


def test_executable_mode_transforms_fenced_and_inline_code():
    text = "Use `x < y` before running:\n```python\nprint(1)\n```"

    choice_html = htmlize_choice(text, render_mode="executable")
    item_html = htmlize_item_text(text, render_mode="executable")
    plain_text = plaintext_item_text(text, render_mode="executable")

    assert "<code>x &lt; y</code>" in choice_html
    assert '<code class="language-python">' in choice_html
    assert 'span style="color: #66D9EF;">print</span>' in choice_html
    assert "<code>x &lt; y</code>" in item_html
    assert "```" not in item_html
    assert plain_text == "Use x < y before running:\nprint(1)"


def test_passage_numbering_preserves_prose_and_poetry_behavior():
    prose = "First paragraph.\n\nSecond paragraph."
    poetry = "Bright moon\nSoft rain\nLong road\nStill lake\nCold dawn"

    numbered_prose, prose_type = add_passage_numbering(prose)
    numbered_poetry, poetry_type = add_passage_numbering(poetry)

    assert prose_type == "prose"
    assert numbered_prose == "{PARANUM:1}     First paragraph.\n\n{PARANUM:2}     Second paragraph."
    assert poetry_type == "poetry"
    assert numbered_poetry == (
        "{LINENUM: 1}     Bright moon\n"
        "               Soft rain\n"
        "               Long road\n"
        "               Still lake\n"
        "{LINENUM: 5}     Cold dawn"
    )


def test_htmlize_prompt_renders_excerpt_numbering_for_prose_and_poetry():
    prose_html = htmlize_prompt(
        "First paragraph.\n\nSecond paragraph.",
        render_mode="executable",
    )
    poetry_html = htmlize_prompt(
        "```poetry\nBright moon\nSoft rain\nLong road\nStill lake\nCold dawn\n```",
        render_mode="executable",
    )

    assert '<span style="font-size: 0.85em; font-style: italic; color: #999; font-weight: normal;">[1]</span>' in prose_html
    assert '<span style="font-size: 0.85em; font-style: italic; color: #999; font-weight: normal;">[2]</span>' in prose_html
    assert '<span style="font-size: 0.85em; font-style: italic; color: #999; font-weight: normal;"> 1</span>' in poetry_html
    assert '<span style="font-size: 0.85em; font-style: italic; color: #999; font-weight: normal;"> 5</span>' in poetry_html


def test_existing_html_code_blocks_receive_syntax_highlighting():
    html = "<pre><code>def f():\n    return 1</code></pre>"

    highlighted_direct = apply_syntax_highlighting_to_html(html)
    highlighted_prompt = htmlize_prompt(html, render_mode="executable")

    assert 'span style="color: #F92672;">return</span>' in highlighted_direct
    assert highlighted_prompt == highlighted_direct


def test_qti_builder_uses_html_formatter_facade():
    question = MCQuestion(
        qtype="MC",
        prompt="Use `x < y`.",
        render_mode="executable",
        choices=[MCChoice(text="True", correct=True), MCChoice(text="False")],
        forced_ident="html_facade_mc",
    )
    quiz = Quiz(title="HTML Formatter Facade", questions=[question])

    xml = build_assessment_xml(quiz)
    root = ET.fromstring(xml)
    ns = {"qti": root.tag.split("}")[0].strip("{")}
    mattext = root.find(".//qti:item/qti:presentation/qti:material/qti:mattext", ns)

    assert mattext is not None
    assert "<code>x &lt; y</code>" in (mattext.text or "")
