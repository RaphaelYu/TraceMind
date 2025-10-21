from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tm.dsl import compile_paths
from tm.runtime import ProcessEngine, ProcessEngineOptions, run_ir_flow
from tm.dsl.runtime import PythonEngine
from tm.runtime.engine import configure_engine as configure_runtime_engine
from tm.runtime.config import load_runtime_config

WDL_SAMPLE = """
version: dsl/v0
workflow: sample
steps:
  - decide(policy.apply):
      values:
        temperature: 72
  - emit(dsl.emit):
      decision: $step.decide
outputs:
  result: $step.decide
"""

PDL_SAMPLE = """
version: pdl/v0
arms:
  default:
    action_on_violation: PASS
evaluate:
  action = arms.default.action_on_violation
emit:
  action: action
"""


@pytest.fixture
def compiled_ir(tmp_path: Path) -> Path:
    src_dir = tmp_path / "dsl"
    src_dir.mkdir()
    (src_dir / "sample.wdl").write_text(WDL_SAMPLE.strip(), encoding="utf-8")
    (src_dir / "sample.pdl").write_text(PDL_SAMPLE.strip(), encoding="utf-8")
    out_dir = tmp_path / "out"
    compile_paths([src_dir], out_dir=out_dir, force=True, emit_ir=True)
    return out_dir / "manifest.json"


def test_run_ir_with_python_engine(compiled_ir: Path) -> None:
    configure_runtime_engine(load_runtime_config())
    result = run_ir_flow("sample", manifest_path=compiled_ir, inputs={}, engine=PythonEngine())
    assert result.status == "completed"


def test_run_ir_with_process_engine(compiled_ir: Path) -> None:
    executor = Path(__file__).resolve().parents[2] / "tm" / "executors" / "mock_process_engine.py"
    options = ProcessEngineOptions(executor_path=executor)
    engine = ProcessEngine(options)
    result = run_ir_flow("sample", manifest_path=compiled_ir, inputs={}, engine=engine)
    assert result.status == "completed"


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    repo_root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = repo_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(args, capture_output=True, text=True, cwd=str(cwd), env=env)


def test_runtime_cli_run_python(compiled_ir: Path) -> None:
    manifest_dir = compiled_ir.parent
    result = _run_cli(
        [
            sys.executable,
            "-m",
            "tm.cli",
            "runtime",
            "run",
            "--manifest",
            str(compiled_ir),
            "--flow",
            "sample",
        ],
        cwd=manifest_dir,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"


def test_runtime_cli_run_process_engine(compiled_ir: Path) -> None:
    executor = Path(__file__).resolve().parents[2] / "tm" / "executors" / "mock_process_engine.py"
    manifest_dir = compiled_ir.parent
    result = _run_cli(
        [
            sys.executable,
            "-m",
            "tm.cli",
            "--engine",
            "proc",
            "--executor-path",
            str(executor),
            "runtime",
            "run",
            "--manifest",
            str(compiled_ir),
            "--flow",
            "sample",
        ],
        cwd=manifest_dir,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
