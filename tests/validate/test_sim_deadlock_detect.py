from __future__ import annotations

from tm.validate.simulator import simulate


def test_deadlock_on_exclusive_lock():
    flow = {
        "steps": {
            "A": {
                "locks": [
                    {"name": "db", "mode": "exclusive"},
                    {"name": "cache", "mode": "exclusive"},
                ]
            },
            "B": {
                "locks": [
                    {"name": "cache", "mode": "exclusive"},
                    {"name": "db", "mode": "exclusive"},
                ]
            },
        }
    }
    report = simulate(flow, at="2025-10-08T09:00:00", max_concurrency=2)
    assert report["deadlocks"] >= 1


def test_simulation_completes_without_deadlock():
    flow = {
        "steps": {
            "A": {"locks": [{"name": "db", "mode": "exclusive"}], "next": ["B"]},
            "B": {"locks": [{"name": "db", "mode": "shared"}]},
        }
    }
    report = simulate(flow, seed=42, max_concurrency=1)
    assert report["deadlocks"] == 0
    assert report["finished"] == 2
