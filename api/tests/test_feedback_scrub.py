"""Offline tests for the feedback tools scrub engine.

Tests replacement-map building, text scrubbing, collision detection, and
verify-clean. All synthetic data, no PII.
"""
import os

from api.feedback_vault import Vault
from api import feedback_scrub as scrub


def _vault_with_students(tmp_path):
    """Helper: populate a vault with a few students."""
    v = Vault(str(tmp_path / "vault.json"))
    v.get_or_assign("9001", "Jose Flores", "5001")
    v.get_or_assign("9002", "Maria Gonzalez", "5002")
    v.get_or_assign("9003", "Romeo Montague", "5003")
    v.set_nicknames("9001", ["Paco"])
    v.set_nicknames("9003", ["Romy"])
    return v


def test_jose_flores_scrub_in_sentence(tmp_path):
    """Full name 'Jose Flores' is replaced with the fake pseudonym."""
    v = _vault_with_students(tmp_path)
    rmap = scrub.build_replacement_map(v.entries(), set())
    text = "Jose Flores wrote a great essay."
    result = scrub.scrub_text(text, rmap)
    assert "Jose Flores" not in result
    e = v.entries()[0]
    assert e["pseudo_first"] in result or e["pseudonym"] in result


def test_nickname_scrubbed(tmp_path):
    """Nickname 'Paco' is replaced with the fake first name."""
    v = _vault_with_students(tmp_path)
    rmap = scrub.build_replacement_map(v.entries(), set())
    text = "My friend Paco helped me."
    result = scrub.scrub_text(text, rmap)
    assert "Paco" not in result


def test_protected_literary_name_preserved_when_no_roster_collision(tmp_path):
    """A protected literary name with no roster collision is preserved."""
    v = _vault_with_students(tmp_path)
    protected = {"katniss", "peeta", "gale"}
    rmap = scrub.build_replacement_map(v.entries(), protected)
    text = "I think Katniss is brave."
    result = scrub.scrub_text(text, rmap)
    assert "Katniss" in result


def test_roster_name_colliding_with_protected_is_scrubbed(tmp_path):
    """Romeo is both a student and a literary character — roster wins, it's scrubbed."""
    v = _vault_with_students(tmp_path)
    protected = {"romeo", "juliet"}
    rmap = scrub.build_replacement_map(v.entries(), protected)
    text = "Romeo Montague wrote about love."
    result = scrub.scrub_text(text, rmap)
    assert "Romeo Montague" not in result
    assert "Romeo" not in result


def test_cross_student_mention(tmp_path):
    """'I worked with Jose' gets scrubbed even though Jose is a different student."""
    v = _vault_with_students(tmp_path)
    rmap = scrub.build_replacement_map(v.entries(), set())
    text = "I worked with Jose."
    result = scrub.scrub_text(text, rmap)
    assert "Jose" not in result


def test_possessive_handled(tmp_path):
    """\"Jose's\" becomes \"Pseudo_first's\" (possessive drops out naturally)."""
    v = _vault_with_students(tmp_path)
    rmap = scrub.build_replacement_map(v.entries(), set())
    text = "Jose's essay was great."
    result = scrub.scrub_text(text, rmap)
    assert "Jose" not in result


def test_verify_clean_returns_empty_on_scrubbed(tmp_path):
    """verify_clean returns [] on properly scrubbed output."""
    v = _vault_with_students(tmp_path)
    rmap = scrub.build_replacement_map(v.entries(), set())
    text = "Jose Flores wrote about courage."
    scrubbed = scrub.scrub_text(text, rmap)
    survivors = scrub.verify_clean(scrubbed, v)
    assert survivors == []


def test_verify_clean_finds_survivors_on_unscrubbed(tmp_path):
    """verify_clean returns surviving tokens on un-scrubbed input."""
    v = _vault_with_students(tmp_path)
    text = "Jose Flores wrote about courage."
    survivors = scrub.verify_clean(text, v)
    assert len(survivors) >= 1


def test_find_collisions_literary(tmp_path):
    """Romeo Montague shows up as a literary collision."""
    v = _vault_with_students(tmp_path)
    protected = {"romeo", "juliet", "tybalt"}
    collisions = scrub.find_collisions(v.entries(), protected)
    assert any("Romeo" in c for c in collisions["literary"])


def test_find_collisions_common_word(tmp_path):
    """Short tokens or common-word tokens appear in common_word collisions."""
    v = Vault(str(tmp_path / "vault2.json"))
    v.get_or_assign("9010", "Will Power", "5010")    # "will" is a common word
    collisions = scrub.find_collisions(v.entries(), set())
    assert any("Will" in c for c in collisions["common_word"])


def test_empty_protected_set_is_valid(tmp_path):
    """Empty protected set is valid — nothing is preserved."""
    v = _vault_with_students(tmp_path)
    rmap = scrub.build_replacement_map(v.entries(), set())
    assert len(rmap) > 0


def test_longest_pattern_wins(tmp_path):
    """Full name pattern beats single-token patterns."""
    v = Vault(str(tmp_path / "vault3.json"))
    v.get_or_assign("9020", "Anne-Marie Smith", "5020")
    v.set_nicknames("9020", ["Anne"])
    rmap = scrub.build_replacement_map(v.entries(), set())
    text = "Anne-Marie Smith is here. Anne is here too."
    result = scrub.scrub_text(text, rmap)
    # Full name should be replaced uniformly
    assert "Anne-Marie Smith" not in result
    assert "Anne-Marie" not in result
