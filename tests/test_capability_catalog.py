from pathlib import Path

import pytest

from tm.caps import CapabilityAlreadyExists, CapabilityCatalog


def _sample_capability() -> dict:
    return {
        "capability_id": "compute.process",
        "version": "1.0.0",
        "description": "Compute in-memory",
        "inputs": {
            "input_data": {"type": "string", "required": True},
        },
        "outputs": {"result": {"type": "string"}},
        "event_types": [
            {"name": "compute.process.done"},
        ],
        "state_extractors": [
            {
                "from_event": "compute.process.done",
                "produces": {
                    "computation.completed": {"type": "boolean", "value": True},
                },
            }
        ],
        "safety_contract": {
            "determinism": True,
            "side_effects": ["none"],
            "rollback": {"supported": False},
        },
    }


def test_register_and_list(tmp_path: Path) -> None:
    catalog_path = tmp_path / "caps.json"
    catalog = CapabilityCatalog(path=catalog_path)
    spec = _sample_capability()

    entry = catalog.register(spec)
    assert entry.capability_id == "compute.process"
    entries = catalog.list()
    assert len(entries) == 1
    assert entries[0].capability_id == "compute.process"
    assert catalog.exists("compute.process")

    loaded = catalog.get("compute.process")
    assert loaded["version"] == spec["version"]


def test_register_conflict_requires_overwrite(tmp_path: Path) -> None:
    catalog_path = tmp_path / "caps.json"
    catalog = CapabilityCatalog(path=catalog_path)
    spec = _sample_capability()
    catalog.register(spec)
    with pytest.raises(CapabilityAlreadyExists):
        catalog.register(spec)
