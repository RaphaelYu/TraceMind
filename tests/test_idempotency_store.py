from __future__ import annotations

from pathlib import Path

from tm.runtime.idempotency import IdempotencyResult, IdempotencyStore


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def tick(self) -> float:
        return self.value

    def advance(self, delta: float) -> None:
        self.value += delta


def test_idempotency_store_roundtrip(tmp_path: Path):
    clock = _Clock()
    store = IdempotencyStore(dir_path=str(tmp_path), capacity=8, snapshot_interval=0.1, clock=clock.tick)
    result = IdempotencyResult(status="ok", output={"value": 42})
    store.remember("k1", result, ttl_seconds=10.0)
    cached = store.get("k1")
    assert cached is not None
    assert cached.status == "ok"
    assert cached.output["value"] == 42

    clock.advance(20.0)
    expired = store.get("k1")
    assert expired is None

    store.prune()
    # Ensure snapshot file exists after prune
    assert (tmp_path / "idempotency.json").exists()
