"""Offline tests for FeedbackExpert vault v2: fake-name pseudonyms, nicknames,
collision avoidance, entries() shape, regenerate.
"""
import json
import os

from api.feedback_vault import Vault


def test_v2_pseudonym_is_fake_name_not_sequential(tmp_path):
    """v2 should assign a multi-word fake name, not 'S001'."""
    v = Vault(str(tmp_path / "vault.json"))
    p = v.get_or_assign("9001", "Ada Lovelace", "5001")
    assert p.count(" ") >= 1          # "Sparky McGee" — at least first + last
    assert not p.startswith("S0")     # not the old scheme


def test_stable_across_calls(tmp_path):
    """Same canvas_id returns the same pseudonym."""
    v = Vault(str(tmp_path / "vault.json"))
    p1 = v.get_or_assign("9001", "Ada Lovelace", "5001")
    p2 = v.get_or_assign("9001")
    assert p1 == p2


def test_persists(tmp_path):
    """Save + reload preserves pseudonyms."""
    vpath = str(tmp_path / "vault.json")
    v = Vault(vpath)
    p1 = v.get_or_assign("9001", "Ada Lovelace", "5001")
    v.save()

    v2 = Vault(vpath)
    assert v2.get_or_assign("9001") == p1
    assert v2.reverse(p1)["real_name"] == "Ada Lovelace"


def test_nicknames_round_trip(tmp_path):
    """Nicknames are stored and appear in all_real_identifiers()."""
    v = Vault(str(tmp_path / "vault.json"))
    v.get_or_assign("9001", "Jose Flores", "5001")
    v.set_nicknames("9001", ["Paco", "Josey"])
    names, ids = v.all_real_identifiers()
    assert "Paco" in names
    assert "Josey" in names
    assert "Jose Flores" in names


def test_nicknames_dedup_and_strip(tmp_path):
    """Nicknames are deduplicated and empty strings removed."""
    v = Vault(str(tmp_path / "vault.json"))
    v.get_or_assign("9001", "Jose Flores", "5001")
    v.set_nicknames("9001", ["Paco", "paco", "", "  ", "Paco"])
    entry = v._by_id["9001"]
    assert entry["nicknames"] == ["Paco"]  # deduped and lowercase kept? no, original case


def test_all_real_identifiers_includes_nicknames(tmp_path):
    """all_real_identifiers includes nicknames in the names set."""
    v = Vault(str(tmp_path / "vault.json"))
    v.get_or_assign("9001", "Jose Flores", "5001")
    v.set_nicknames("9001", ["Paco"])
    v.get_or_assign("9002", "Maria Gonzalez")
    v.set_nicknames("9002", ["Mari"])
    names, ids = v.all_real_identifiers()
    assert "Paco" in names
    assert "Mari" in names
    assert "Jose Flores" in names
    assert "Maria Gonzalez" in names


def test_entries_shape(tmp_path):
    """entries() returns list of dicts with the expected keys, sorted by real_name."""
    v = Vault(str(tmp_path / "vault.json"))
    v.get_or_assign("9002", "Maria Gonzalez")
    v.get_or_assign("9001", "Ada Lovelace", "5001")
    v.set_nicknames("9001", ["Ada"])
    entries = v.entries()
    assert len(entries) == 2
    # Sorted by real_name
    assert entries[0]["real_name"] == "Ada Lovelace"
    assert entries[1]["real_name"] == "Maria Gonzalez"
    row = entries[0]
    assert "canvas_id" in row
    assert "pseudonym" in row
    assert "pseudo_first" in row
    assert "pseudo_last" in row
    assert "nicknames" in row
    assert row["nicknames"] == ["Ada"]


def test_set_pseudonym_override(tmp_path):
    """Manual override changes the pseudonym."""
    v = Vault(str(tmp_path / "vault.json"))
    v.get_or_assign("9001", "Jose Flores", "5001")
    v.set_pseudonym("9001", "Custom", "Name")
    assert v.get_or_assign("9001") == "Custom Name"
    e = v._by_id["9001"]
    assert e["pseudo_first"] == "Custom"
    assert e["pseudo_last"] == "Name"


def test_regenerate_produces_different_name(tmp_path):
    """Regenerate creates a different fake name."""
    v = Vault(str(tmp_path / "vault.json"))
    orig = v.get_or_assign("9001", "Jose Flores", "5001")
    v.regenerate_pseudonym("9001")
    new = v.get_or_assign("9001")
    assert new != orig


def test_fake_name_no_collision_with_roster(tmp_path):
    """Fake name shouldn't contain a real roster token."""
    v = Vault(str(tmp_path / "vault.json"))
    roster = {"Jose Flores", "Maria Gonzalez", "Student Name"}
    p = v.get_or_assign("9001", "Jose Flores", "5001", roster_names=roster)
    pseudo_lower = p.lower()
    for name in roster:
        for token in name.lower().split():
            assert token not in pseudo_lower.split(), \
                f"Fake name '{p}' contains real roster token '{token}'"


def test_reverse_unknown_returns_none(tmp_path):
    """Reverse for an unknown pseudonym returns None."""
    v = Vault(str(tmp_path / "vault.json"))
    assert v.reverse("Nobody") is None


def test_empty_vault_is_usable(tmp_path):
    """Empty vault works."""
    v = Vault(str(tmp_path / "vault.json"))
    assert len(v) == 0
    assert v.entries() == []
    names, ids = v.all_real_identifiers()
    assert names == set()
    assert ids == set()
