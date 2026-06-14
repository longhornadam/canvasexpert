import json
import pytest

parser_mod = pytest.importorskip("dev.newspec_engine.parser")
packager_mod = pytest.importorskip("dev.newspec_engine.packager")
parse_news_json = parser_mod.parse_news_json
package_quiz = packager_mod.package_quiz


def test_extensions_passthrough_pipeline():
    text = """
    chatter before
    <QUIZFORGE_JSON>
    {
      "version": "3.0-json",
      "title": "Ext Test",
      "metadata": {
        "extensions": {
          "world": { "room_layout": "linear" }
        }
      },
      "items": [
        {
          "id": "q1",
          "type": "MC",
          "prompt": "P?",
          "choices": [
            {"text": "A", "correct": true},
            {"text": "B", "correct": false}
          ],
          "metadata": {
            "extensions": {
              "world": { "room": 1 }
            }
          }
        }
      ],
      "rationales": [
        {"item_id": "q1", "correct": "A is correct", "distractor": "B misses key detail"}
      ]
    }
    </QUIZFORGE_JSON>
    chatter after
    """
    quiz = parse_news_json(text)
    assert quiz.metadata["extensions"]["world"]["room_layout"] == "linear"
    assert quiz.items[0]["metadata"]["extensions"]["world"]["room"] == 1

    packaged = package_quiz(quiz)
    assert packaged.metadata["extensions"]["world"]["room_layout"] == "linear"
    assert packaged.items[0]["metadata"]["extensions"]["world"]["room"] == 1
    # exporter ignores metadata unless explicitly used; here we simply ensure it survives
    assert packaged.rationales[0].item_id == "q1"
