from types import SimpleNamespace

from engine.core.questions import FITBQuestion
from engine.importers import _packaged_to_domain


def _packaged(items):
    return SimpleNamespace(items=items, rationales=[], title="Test Quiz")


def test_fitb_single_blank_accepts_string_list():
    packaged = _packaged(
        [
            {
                "type": "FITB",
                "prompt": "A search is [blank].",
                "accept": ["linear search", "sequential search"],
            }
        ]
    )

    quiz = _packaged_to_domain(packaged)
    fitb = quiz.questions[0]

    assert isinstance(fitb, FITBQuestion)
    assert fitb.variants == ["linear search", "sequential search"]
    assert fitb.variants_per_blank == []
    assert "[blank]" not in fitb.prompt


def test_fitb_multi_blank_accept_arrays():
    packaged = _packaged(
        [
            {
                "type": "FITB",
                "prompt": "Mix [blank1] then [blank2].",
                "accept": [["red", "crimson"], ["blue"]],
                "answer_mode": "open_entry",
            }
        ]
    )

    quiz = _packaged_to_domain(packaged)
    fitb = quiz.questions[0]

    assert isinstance(fitb, FITBQuestion)
    assert fitb.variants == ["red", "crimson", "blue"]
    assert fitb.variants_per_blank == [["red", "crimson"], ["blue"]]
    assert len(fitb.blank_tokens) == 2
    assert "[blank1]" not in fitb.prompt
    assert "[blank2]" not in fitb.prompt
