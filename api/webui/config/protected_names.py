"""Protected-names store — literary character packs and custom protected names.

Uses lazy module-reference so monkeypatches to config._io propagate correctly.
"""
from . import _io as _io_mod

LITERARY_PACKS = [
    {"id": "outsiders",  "title": "The Outsiders",
     "names": ["Ponyboy","Johnny","Dally","Dallas","Sodapop","Darry","Two-Bit","Cherry","Bob"]},
    {"id": "hunger_games","title": "The Hunger Games",
     "names": ["Katniss","Peeta","Gale","Prim","Haymitch","Effie","Rue","Cinna","Snow"]},
    {"id": "giver",       "title": "The Giver",
     "names": ["Jonas","Asher","Fiona","Gabriel","Lily"]},
    {"id": "romeo_juliet","title": "Romeo & Juliet",
     "names": ["Romeo","Juliet","Tybalt","Mercutio","Benvolio","Capulet","Montague","Friar"]},
]


def list_protected_packs() -> list[dict]:
    enabled = _io_mod._synced_state().get("protected_packs_enabled", {})
    return [
        {"id": p["id"], "title": p["title"], "names": p["names"],
         "enabled": enabled.get(p["id"], False)}
        for p in LITERARY_PACKS
    ]


def set_pack_enabled(pack_id: str, enabled: bool):
    state = _io_mod._synced_state()
    enabled_map = state.get("protected_packs_enabled", {})
    enabled_map[pack_id] = enabled
    _io_mod._save_synced_key("protected_packs_enabled", enabled_map)


def get_custom_protected_names() -> list[str]:
    return list(_io_mod._synced_state().get("protected_names_custom", []))


def set_custom_protected_names(names: list[str]):
    clean = sorted(set(n.strip() for n in names if n and n.strip()))
    _io_mod._save_synced_key("protected_names_custom", clean)


def active_protected_names() -> set[str]:
    result: set[str] = set()
    for p in list_protected_packs():
        if p["enabled"]:
            result.update(n.lower() for n in p["names"])
    for n in get_custom_protected_names():
        result.add(n.lower())
    return result