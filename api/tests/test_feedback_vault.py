"""Offline tests for feedback tools vault v3: one-word registry pseudonyms,
nicknames, collision avoidance, entries() shape, regenerate, and the
schema-v3 clean-break fail-closed law.

See `docs/contracts/pseudonym-contract.md` for the full contract this file
pins.
"""
import json

import pytest

from api import feedback_vault as fv
from api.feedback_vault import (
    InvalidPseudonymError,
    PseudonymCollisionError,
    PseudonymRegistryError,
    Vault,
    VaultSchemaError,
)

_WORDS = fv._REGISTRY_WORDS  # already validated at import time; reused, never mutated


# --- registry law -----------------------------------------------------------

# Species the contract permanently excludes: the word itself is not an
# acceptable thing to call a student. Jynx is a racial caricature; the trash /
# sludge / stink species and Hypno read as an insult or worse next to a child's
# own work. See docs/contracts/pseudonym-contract.md.
_EXCLUDED_SPECIES = {
    "jynx",
    "grimer", "muk", "trubbish", "garbodor", "stunky", "skuntank",
    "hypno",
    "snorlax", "swinub", "piloswine", "phanpy", "donphan", "miltank",
    "makuhita", "hariyama", "gulpin", "swalot", "wailmer", "wailord",
    "purugly", "munchlax", "hippopotas", "hippowdon", "lickilicky", "mamoswine",
    "tepig", "pignite", "emboar", "guzzlord", "greedent", "cufant", "copperajah",
    "lechonk", "oinkologne", "cetoddle", "cetitan",
    "slowpoke", "slowbro", "slowking", "numel", "magikarp", "wobbuffet",
}


def test_registry_meets_the_locked_contract():
    """Exactly the 'pokemon' category, at least 256 unique, ASCII title-case
    single-token words, no duplicate, and every excluded species absent."""
    with open(fv._REGISTRY_PATH, encoding="utf-8") as f:
        data = json.load(f)

    assert set(data) == {"pokemon"}
    seen: set[str] = set()
    for category, words in data.items():
        assert isinstance(words, list) and words, category
        for word in words:
            assert fv._WORD_RE.fullmatch(word), f"{word!r} in {category}"
            assert word.isascii()
            folded = word.lower()
            assert folded not in seen, f"{word!r} duplicated in the registry"
            seen.add(folded)

    assert len(seen) >= 256
    assert seen & _EXCLUDED_SPECIES == set()


@pytest.mark.parametrize("bad_doc", [
    {},                                          # missing 'pokemon'
    {"pokemon": _WORDS, "mineral": _WORDS[:1]},  # unexpected extra category
    {"pokemon": []},                             # empty category
    {"pokemon": _WORDS[:1]},                     # far below 256 total
    {"pokemon": _WORDS + [_WORDS[0]]},           # duplicated entry
    {"pokemon": _WORDS + ["not-a-word"]},        # not title-case ASCII
    {"pokemon": _WORDS + ["Two Words"]},         # multiword entry
])
def test_registry_loader_fails_closed_on_structural_problems(tmp_path, monkeypatch, bad_doc):
    path = tmp_path / "bad_registry.json"
    path.write_text(json.dumps(bad_doc), encoding="utf-8")
    monkeypatch.setattr(fv, "_REGISTRY_PATH", str(path))
    with pytest.raises(PseudonymRegistryError):
        fv._load_registry()


# --- registry runway ---------------------------------------------------------
# No delete/prune/release path exists on purpose (see the module docstring), so
# these tests pin the forecast that exists instead: the shape of
# `registry_runway()` and the exact boundary where `low_runway` flips.

def test_registry_runway_shape_and_arithmetic():
    total = len(_WORDS)
    result = fv.registry_runway(10)
    assert result == {
        "words_total": total,
        "words_assigned": 10,
        "words_remaining": total - 10,
        "low_runway": False,
    }


def test_registry_runway_clamps_a_negative_assigned_count_to_zero():
    result = fv.registry_runway(-5)
    assert result["words_assigned"] == 0
    assert result["words_remaining"] == len(_WORDS)
    assert result["low_runway"] is False


def test_registry_runway_never_reports_negative_remaining_on_over_assignment():
    """Should never happen in practice -- `_select_available_word` fails
    closed before the vault could hold more entries than the registry has
    words -- but the forecast must not go negative if it ever did."""
    total = len(_WORDS)
    result = fv.registry_runway(total + 50)
    assert result["words_remaining"] == 0
    assert result["low_runway"] is True


def test_registry_runway_flips_low_exactly_at_the_threshold_boundary(monkeypatch):
    """Concrete, easy-to-verify boundary: a 10-word registry with the real
    20% low-runway fraction has a threshold of 2 words remaining. One word
    above that threshold reads ready; at or below it reads low."""
    monkeypatch.setattr(fv, "_REGISTRY_WORDS", list(_WORDS[:10]))
    assert fv.registry_runway(7) == {
        "words_total": 10, "words_assigned": 7, "words_remaining": 3,
        "low_runway": False,
    }
    assert fv.registry_runway(8) == {
        "words_total": 10, "words_assigned": 8, "words_remaining": 2,
        "low_runway": True,
    }


def test_registry_runway_flips_low_at_the_real_registry_threshold():
    """Same boundary, but against the real registry size rather than a
    monkeypatched one, so a future registry resize cannot silently make this
    test meaningless."""
    total = len(_WORDS)
    threshold = round(total * fv._LOW_RUNWAY_FRACTION)
    assert fv.registry_runway(total - threshold - 1)["low_runway"] is False
    assert fv.registry_runway(total - threshold)["low_runway"] is True


def test_empty_vault_reports_full_runway_and_not_low(tmp_path):
    v = Vault(str(tmp_path / "vault.json"))
    result = v.registry_runway()
    assert result["words_assigned"] == 0
    assert result["words_remaining"] == len(_WORDS)
    assert result["low_runway"] is False


def test_vault_registry_runway_counts_this_vaults_own_assignments(tmp_path):
    v = Vault(str(tmp_path / "vault.json"))
    v.get_or_assign("9001", "Student One")
    v.get_or_assign("9002", "Student Two")
    result = v.registry_runway()
    assert result["words_assigned"] == 2
    assert result["words_remaining"] == len(_WORDS) - 2
    assert result["words_total"] == len(_WORDS)


# --- assignment law ----------------------------------------------------------

def test_assigned_pseudonym_is_an_available_registry_word_stable_and_unique(tmp_path):
    vpath = str(tmp_path / "vault.json")
    v = Vault(vpath)
    p1 = v.get_or_assign("9001", "Ada Lovelace", "5001")
    p2 = v.get_or_assign("9002", "Alan Turing", "5002")

    assert p1.lower() in {w.lower() for w in _WORDS}
    assert p2.lower() in {w.lower() for w in _WORDS}
    assert p1 != p2
    assert v.get_or_assign("9001") == p1          # stable on re-sight

    v.save()
    v2 = Vault(vpath)
    assert v2.get_or_assign("9001") == p1         # stable after persistence
    assert v2.reverse(p1)["real_name"] == "Ada Lovelace"


def test_get_or_assign_avoids_supplied_roster_name_tokens(tmp_path):
    v = Vault(str(tmp_path / "vault.json"))
    banned_word = _WORDS[0]
    pseudonym = v.get_or_assign("9001", "Roster Student",
                                roster_names={f"Roster {banned_word}"})
    assert pseudonym.lower() != banned_word.lower()


def test_exhaustion_fails_closed_rather_than_synthesizing(tmp_path, monkeypatch):
    """Never a placeholder or numbered word on exhaustion."""
    monkeypatch.setattr(fv, "_REGISTRY_WORDS", [_WORDS[0]])
    v = Vault(str(tmp_path / "vault.json"))
    v.get_or_assign("9001", "First Student")      # takes the only word
    with pytest.raises(PseudonymRegistryError):
        v.get_or_assign("9002", "Second Student")


def test_empty_vault_is_usable(tmp_path):
    v = Vault(str(tmp_path / "vault.json"))
    assert len(v) == 0
    assert v.entries() == []
    names, ids = v.all_real_identifiers()
    assert names == set()
    assert ids == set()


def test_reverse_unknown_returns_none(tmp_path):
    v = Vault(str(tmp_path / "vault.json"))
    assert v.reverse("Nobody") is None


# --- schema-v3 clean break: fail closed on a retired-shape document ---------

def test_missing_vault_file_starts_empty(tmp_path):
    v = Vault(str(tmp_path / "vault.json"))
    assert len(v) == 0


def test_present_document_missing_schema_version_fails_closed(tmp_path):
    path = tmp_path / "vault.json"
    path.write_text(json.dumps({"by_canvas_id": {}}), encoding="utf-8")
    with pytest.raises(VaultSchemaError):
        Vault(str(path))


def test_present_document_with_retired_pseudo_first_field_fails_closed(tmp_path):
    """The only permitted source reference to pseudo_first/pseudo_last: an
    explicit fail-closed rejection of the retired two-part shape."""
    path = tmp_path / "vault.json"
    path.write_text(json.dumps({
        "schema_version": 3,
        "by_canvas_id": {
            "9001": {
                "pseudonym": _WORDS[0], "pseudo_first": "Old", "pseudo_last": "Shape",
                "real_name": "Retired Shape", "sis_id": "", "nicknames": [],
            },
        },
    }), encoding="utf-8")
    with pytest.raises(VaultSchemaError):
        Vault(str(path))


# --- nicknames ----------------------------------------------------------------

def test_nicknames_round_trip(tmp_path):
    v = Vault(str(tmp_path / "vault.json"))
    v.get_or_assign("9001", "Jose Flores", "5001")
    v.set_nicknames("9001", ["Paco", "Josey"])
    names, ids = v.all_real_identifiers()
    assert "Paco" in names
    assert "Josey" in names
    assert "Jose Flores" in names


def test_nicknames_dedup_and_strip(tmp_path):
    v = Vault(str(tmp_path / "vault.json"))
    v.get_or_assign("9001", "Jose Flores", "5001")
    v.set_nicknames("9001", ["Paco", "paco", "", "  ", "Paco"])
    entry = v._by_id["9001"]
    assert entry["nicknames"] == ["Paco"]


def test_all_real_identifiers_includes_nicknames(tmp_path):
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


# --- entries() shape ----------------------------------------------------------

def test_entries_shape(tmp_path):
    """entries() returns list of dicts with exactly the schema-v3 fields,
    sorted by real_name -- no retired pseudo_first/pseudo_last component."""
    v = Vault(str(tmp_path / "vault.json"))
    v.get_or_assign("9002", "Maria Gonzalez")
    v.get_or_assign("9001", "Ada Lovelace", "5001")
    v.set_nicknames("9001", ["Ada"])
    entries = v.entries()
    assert len(entries) == 2
    assert entries[0]["real_name"] == "Ada Lovelace"
    assert entries[1]["real_name"] == "Maria Gonzalez"
    row = entries[0]
    assert set(row) == {"canvas_id", "real_name", "sis_id", "pseudonym", "nicknames", "first_seen"}
    assert row["nicknames"] == ["Ada"]


# --- manual set / regenerate: the same allowlist and collision law ----------

def _two_students(path):
    vault = Vault(str(path))
    vault.get_or_assign("9001", "Synthetic One", "SIS-1")
    vault.set_pseudonym("9001", _WORDS[0])
    vault.get_or_assign("9002", "Synthetic Two", "SIS-2")
    vault.set_pseudonym("9002", _WORDS[1])
    vault.save()
    return vault


def test_set_pseudonym_override(tmp_path):
    v = Vault(str(tmp_path / "vault.json"))
    v.get_or_assign("9001", "Jose Flores", "5001")
    v.set_pseudonym("9001", _WORDS[2])
    assert v.get_or_assign("9001") == _WORDS[2]


def test_set_pseudonym_normalizes_case_to_the_registry_entry(tmp_path):
    v = Vault(str(tmp_path / "vault.json"))
    v.get_or_assign("9001", "Jose Flores", "5001")
    v.set_pseudonym("9001", _WORDS[3].upper())
    assert v.get_or_assign("9001") == _WORDS[3]


@pytest.mark.parametrize("bad_value", [
    "",
    "   ",
    "Two Words",
    123,
    None,
    "Notarealregistryword",
])
def test_set_pseudonym_rejects_invalid_values_without_mutating_the_vault(tmp_path, bad_value):
    v = Vault(str(tmp_path / "vault.json"))
    original = v.get_or_assign("9001", "Jose Flores", "5001")
    with pytest.raises(InvalidPseudonymError):
        v.set_pseudonym("9001", bad_value)
    assert v.get_or_assign("9001") == original


def test_regenerate_produces_a_different_available_registry_word(tmp_path):
    v = Vault(str(tmp_path / "vault.json"))
    orig = v.get_or_assign("9001", "Jose Flores", "5001")
    v.regenerate_pseudonym("9001")
    new = v.get_or_assign("9001")
    assert new != orig
    assert new.lower() in {w.lower() for w in _WORDS}


def test_set_pseudonym_refuses_a_name_another_student_holds(tmp_path):
    """Without this, two entries share a pseudonym and the reverse index
    resolves to whichever was written last, attaching one student's work to
    another."""
    vault = _two_students(tmp_path / "vault.json")
    with pytest.raises(PseudonymCollisionError):
        vault.set_pseudonym("9002", _WORDS[0])


def test_set_pseudonym_allows_a_student_to_keep_their_own_name(tmp_path):
    """Re-setting a student to the name they already hold, or changing only its
    capitalization, is not a collision."""
    vault = _two_students(tmp_path / "vault.json")
    vault.set_pseudonym("9001", _WORDS[0])
    assert vault.reverse(_WORDS[0])["canvas_id"] == "9001"
    vault.set_pseudonym("9001", _WORDS[0].upper())
    assert vault.reverse(_WORDS[0])["canvas_id"] == "9001"


def test_a_refused_rename_leaves_the_vault_untouched(tmp_path):
    """The check runs before any mutation, so this holds without relying on the
    transaction to roll back."""
    path = tmp_path / "vault.json"
    vault = _two_students(path)
    before = json.loads(path.read_text(encoding="utf-8"))

    with pytest.raises(PseudonymCollisionError):
        vault.set_pseudonym("9002", _WORDS[0])

    assert vault.reverse(_WORDS[0])["canvas_id"] == "9001"
    assert vault.reverse(_WORDS[1])["canvas_id"] == "9002"
    assert json.loads(path.read_text(encoding="utf-8")) == before

    reloaded = Vault(str(path))
    assert reloaded.reverse(_WORDS[0])["canvas_id"] == "9001"
    assert reloaded.reverse(_WORDS[1])["canvas_id"] == "9002"


def test_a_refused_rename_also_discards_a_nickname_edit_in_the_same_patch(tmp_path):
    """`update_student` applies nicknames and the pseudonym in one transaction,
    and transaction() only saves on the success path. A patch that is refused
    must therefore land nothing at all."""
    path = tmp_path / "vault.json"
    vault = _two_students(path)

    try:
        with vault.transaction():
            vault.set_nicknames("9002", ["Bee"])
            vault.set_pseudonym("9002", _WORDS[0])
    except PseudonymCollisionError:
        pass

    reloaded = Vault(str(path))
    entry = next(e for e in reloaded.entries() if str(e.get("canvas_id")) == "9002")
    assert entry.get("nicknames") == []
    assert reloaded.reverse(_WORDS[1])["canvas_id"] == "9002"
