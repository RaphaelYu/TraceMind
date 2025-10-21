from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tm.dsl import compile_paths

pytest.importorskip("yaml", reason="PyYAML required for DSL compilation")

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


def _write_sample(tmp_path: Path) -> Path:
    src_dir = tmp_path / "dsl"
    src_dir.mkdir()
    (src_dir / "sample.wdl").write_text(WDL_SAMPLE.strip(), encoding="utf-8")
    (src_dir / "sample.pdl").write_text(PDL_SAMPLE.strip(), encoding="utf-8")
    return src_dir


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ}
    repo_root = Path(__file__).resolve().parents[2]
    env["PYTHONPATH"] = str(repo_root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(args, capture_output=True, text=True, cwd=str(cwd), env=env)


def test_verify_online_rebuilds_sources(tmp_path: Path) -> None:
    src_dir = _write_sample(tmp_path)
    out_dir = tmp_path / "artifacts"
    result = _run_cli(
        [
            sys.executable,
            "-m",
            "tm.cli",
            "verify",
            "online",
            "--flow",
            "sample",
            "--sources",
            str(src_dir),
            "--out",
            str(out_dir),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
    assert (out_dir / "manifest.json").exists()


def test_verify_online_uses_existing_manifest(tmp_path: Path) -> None:
    src_dir = _write_sample(tmp_path)
    out_dir = tmp_path / "out" / "dsl"
    out_dir.mkdir(parents=True, exist_ok=True)
    compile_paths([src_dir], out_dir=out_dir, force=True, emit_ir=True)
    manifest = out_dir / "manifest.json"

    result = _run_cli(
        [
            sys.executable,
            "-m",
            "tm.cli",
            "verify",
            "online",
            "--flow",
            "sample",
            "--manifest",
            str(manifest),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
