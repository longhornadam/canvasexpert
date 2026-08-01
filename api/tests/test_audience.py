from api import audience


def test_learning_objective_is_classified_classroom_facing():
    item = audience.tag({"kind": "learning_objective", "text": "Use evidence."})
    assert item["audience"] == audience.CLASSROOM
    assert audience.classroom_safe(item)
    assert audience.classroom_only([item]) == [item]
