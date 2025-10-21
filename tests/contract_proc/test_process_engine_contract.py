"""ProcessEngine REP contract tests backed by the mock executor."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from tm.runtime.process_engine import (
    CapabilitiesMismatch,
    ProcessEngine,
    ProcessEngineOptions,
    TransportError,
)


def _executor_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "tm" / "executors" / "mock_process_engine.py"


def _minimal_ir() -> dict:
    return {
        "version": "1.0.0",
        "flow": {"name": "demo.flow", "timeout_ms": 0},
        "constants": {
            "policyRef": "demo.policy",
            "policy": {"policy": {"id": "demo", "strategy": "pdl/v0", "params": {}}},
        },
        "inputs_schema": {},
        "graph": {
            "nodes": [
                {
                    "id": "read",
                    "type": "opcua.read",
                    "with": {"endpoint": "opc.tcp://example", "node_ids": ["ns=2;i=1"]},
                    "timeout_ms": 0,
                    "retry": {"max": 0, "backoff_ms": 0},
                },
                {
                    "id": "emit",
                    "type": "dsl.emit",
                    "with": {"decision": {"status": "ok"}},
                    "timeout_ms": 0,
                    "retry": {"max": 0, "backoff_ms": 0},
                },
            ],
            "edges": [
                {"from": "read", "to": "emit", "on": "success"},
            ],
        },
        "metadata": {"generated_at": "2024-01-01T00:00:00Z", "source_file": "demo.wdl"},
    }


def _options(**kwargs) -> ProcessEngineOptions:
    return ProcessEngineOptions(
        executor_path=_executor_path(),
        python_path=Path(sys.executable),
        **kwargs,
    )


def test_capabilities_handshake_accepts_supported_runtime():
    engine = ProcessEngine(_options(required_steps={"opcua.read", "dsl.emit"}))
    assert isinstance(engine, ProcessEngine)


def test_capabilities_handshake_rejects_missing_step_kind():
    with pytest.raises(CapabilitiesMismatch):
        ProcessEngine(_options(required_steps={"ros.publish"}))


def test_start_run_executes_minimal_flow_successfully():
    engine = ProcessEngine(_options())
    run = engine.start_run(_minimal_ir(), inputs={}, options={"run_id": "run-1"})

    status = None
    for _ in range(10):
        payload = run.poll()
        status = payload["status"]
        if status == "completed":
            break
        time.sleep(0.05)

    run.close()
    assert status == "completed"


def test_transport_breakage_maps_to_transport_error():
    bogus = ProcessEngineOptions(
        executor_path=Path("missing-executor.py"),
        python_path=Path(sys.executable),
    )
    with pytest.raises(TransportError):
        ProcessEngine(bogus)


def test_executor_error_surfaces_as_transport_error(tmp_path: Path):
    script = tmp_path / "executor.py"
    script.write_text("import sys; sys.exit(1)", encoding="utf-8")
    opts = ProcessEngineOptions(executor_path=script, python_path=Path(sys.executable))
    with pytest.raises(TransportError):
        ProcessEngine(opts)
