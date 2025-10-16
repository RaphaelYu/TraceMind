from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tm.dsl.testgen import generate_for_path

PYTHON = sys.executable

WDL_SAMPLE = """
version: dsl/v0
workflow: sample
inputs:
  flag: string
steps:
  - first(op.echo):
      value: 1
  - when $input.flag in ["YES","NO"]:
      branch(op.echo):
        value: 2
  - finish(op.echo):
      value: $step.branch.value
"""

PDL_SAMPLE = """
version: pdl/v0
arms:
  default:
    threshold: 10
    action_on_violation: WRITE_BACK
epsilon: 0.1
evaluate:
  temp := first_numeric(values)
  if temp >= arms.active.threshold:
    action = arms.active.action_on_violation
  else:
    action = "NONE"
emit:
  action: action
"""


def test_generate_for_wdl(tmp_path: Path) -> None:
    path = tmp_path / "sample.wdl"
    path.write_text(WDL_SAMPLE, encoding="utf-8")
    result = generate_for_path(path, output_dir=tmp_path / "fixtures")
    assert result.kind == "wdl"
    assert len(result.cases) >= 6
    assert result.output_dir.exists()
    files = sorted(result.output_dir.glob("case_*.json"))
    assert files, "fixtures not written to disk"
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert "inputs" in payload and "expectations" in payload


def test_generate_for_pdl(tmp_path: Path) -> None:
    path = tmp_path / "policy.pdl"
    path.write_text(PDL_SAMPLE, encoding="utf-8")
    result = generate_for_path(path, output_dir=tmp_path / "fixtures")
    assert result.kind == "pdl"
    assert result.cases  # at least one
    files = sorted(result.output_dir.glob("case_*.json"))
    assert files
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert "values" in payload["inputs"]


def test_cli_testgen(tmp_path: Path) -> None:
    wdl_path = tmp_path / "flow.wdl"
    wdl_path.write_text(WDL_SAMPLE, encoding="utf-8")
    out_dir = tmp_path / "fixtures"
    result = subprocess.run(
        [
            PYTHON,
            "-m",
            "tm.cli",
            "dsl",
            "testgen",
            str(wdl_path),
            "--out",
            str(out_dir),
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["fixtures"][0]["cases"] >= 1
    assert (out_dir / "flow" / "case_01.json").exists()
