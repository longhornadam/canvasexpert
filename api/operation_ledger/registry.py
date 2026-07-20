"""Adapter registry — maps kind strings to adapter instances.

Adapters implement the OperationAdapter protocol from the design doc.
Register new kinds via ``register(adapter)``.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class OperationAdapter(Protocol):
    kind: str

    def build_payload(self, prepare_request: dict) -> dict: ...
    def source_digest(self, payload: dict) -> str: ...
    def verify_targets(self, payload: dict, targets: list[dict]) -> list[dict]: ...
    def target_key(self, payload: dict, course_id: str) -> str: ...
    def idempotency_key(self, payload: dict, course_id: str) -> str: ...
    def freeze_review(self, payload: dict, target: dict, baseline: dict) -> dict: ...
    def check_drift(self, payload: dict, target: dict, baseline: dict) -> bool: ...
    def capture_baseline(self, payload: dict, target: dict) -> dict: ...
    def execute(self, payload: dict, target: dict, baseline: dict, claim: dict,
                context) -> dict: ...
    def reconcile(self, payload: dict, target: dict, baseline: dict) -> dict: ...
    def retry_selector(self, operation: dict) -> list[dict]: ...


_REGISTRY: dict[str, OperationAdapter] = {}


def register(adapter: OperationAdapter) -> None:
    if not hasattr(adapter, "kind") or not adapter.kind:
        raise ValueError("adapter must have a non-empty 'kind' attribute")
    _REGISTRY[adapter.kind] = adapter


def get_adapter(kind: str) -> OperationAdapter:
    adapter = _REGISTRY.get(kind)
    if adapter is None:
        raise ValueError(f"unknown operation kind: {kind}")
    return adapter


def is_registered(kind: str) -> bool:
    return kind in _REGISTRY
