"""Pseudonym resolution for the daily writing store (INV-7).

Records on disk are keyed by Canvas user id, because that key is durable: the
vault lets a teacher regenerate or hand-set a pseudonym, and a store keyed on
the pseudonym string would orphan every stored writing record for
that student the moment they did. Everything above the store speaks pseudonyms
only, and the translation happens here.

The mapping itself lives in Canvas Expert's existing identity vault and
nowhere else. This module holds no mapping of its own: a second mapping would
be a second source of truth, and the two would eventually disagree.
"""
from __future__ import annotations

from typing import Protocol


class IdentityError(KeyError):
    """A pseudonym or canvas id has no counterpart in the vault."""


class IdentityResolver(Protocol):
    def to_canvas_id(self, pseudonym_id: str) -> str: ...

    def to_pseudonym(self, canvas_id: str) -> str: ...


class VaultResolver:
    """Resolver backed by `api.feedback_vault.Vault`.

    Reads only. Minting a pseudonym is the roster sync's job, and a store read
    that silently created identities would hide a roster problem.
    """

    def __init__(self, vault):
        self._vault = vault

    @property
    def vault(self):
        return self._vault

    def to_canvas_id(self, pseudonym_id: str) -> str:
        entry = self._vault.reverse(pseudonym_id)
        if not entry or not entry.get("canvas_id"):
            raise IdentityError(
                f"pseudonym {pseudonym_id!r} is not in the identity vault; "
                "sync the roster for this section first"
            )
        return str(entry["canvas_id"])

    def to_pseudonym(self, canvas_id: str) -> str:
        for entry in self._vault.entries():
            if str(entry.get("canvas_id")) == str(canvas_id):
                pseudonym = entry.get("pseudonym")
                if pseudonym:
                    return pseudonym
        raise IdentityError(
            f"canvas id {canvas_id} has no pseudonym in the identity vault"
        )


class MappingResolver:
    """Explicit two-way mapping, for fixtures and tests.

    Offline and vault-free, which is what keeps the whole substrate testable
    without a workspace or a roster.
    """

    def __init__(self, pseudonym_by_canvas_id: dict[str, str]):
        self._forward = {str(k): v for k, v in pseudonym_by_canvas_id.items()}
        self._reverse = {v: str(k) for k, v in self._forward.items()}
        if len(self._reverse) != len(self._forward):
            raise IdentityError("pseudonyms in the mapping are not unique")

    def to_canvas_id(self, pseudonym_id: str) -> str:
        try:
            return self._reverse[pseudonym_id]
        except KeyError as exc:
            raise IdentityError(f"unknown pseudonym {pseudonym_id!r}") from exc

    def to_pseudonym(self, canvas_id: str) -> str:
        try:
            return self._forward[str(canvas_id)]
        except KeyError as exc:
            raise IdentityError(f"unknown canvas id {canvas_id!r}") from exc
