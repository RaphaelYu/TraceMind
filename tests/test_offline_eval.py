import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("recent_sec", [300.0])
def test_offline_eval_script(tmp_path, recent_sec):
    repo_root = Path(__file__).resolve().parents[1]
    runs_path = repo_root / "tests" / "data" / "sample_runs.jsonl"
    output_path = tmp_path / "offline_eval.json"

    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "offline_eval.py"),
        "--from-jsonl",
        str(runs_path),
        "--baseline-sec",
        "800",
        "--recent-sec",
        str(recent_sec),
        "--output",
        str(output_path),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root, env=env)
    assert result.returncode == 0, result.stderr
    assert "flow_fast" in result.stdout

    payload = json.loads(output_path.read_text("utf-8"))
    bindings = payload["bindings"]
    fast_recent = bindings["demo:read"]["flow_fast"]["recent"]
    slow_recent = bindings["demo:read"]["flow_slow"]["recent"]
    assert fast_recent["n"] > slow_recent["n"]
    fast_delta = bindings["demo:read"]["flow_fast"]["delta"]["avg_reward"]
    slow_delta = bindings["demo:read"]["flow_slow"]["delta"]["avg_reward"]
    assert fast_delta >= 0.0
    assert slow_delta <= fast_delta
