from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _fixture(name: str) -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "flows" / name


def test_plan_reports_stats_json():
    flow_path = _fixture("tiny_ok.yml")
    result = subprocess.run(
        [sys.executable, "-m", "tm", "flow", "plan", str(flow_path), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "flows" in payload
    assert payload["flows"][0]["stats"]["depth"] == 3
    assert payload["flows"][0]["stats"]["nodes"] == 3


def test_plan_errors_on_threshold(monkeypatch):
    flow_path = _fixture("tiny_ok.yml")
    monkeypatch.setenv("TM_FLOW_ERROR_MAX_DEPTH", "1")
    result = subprocess.run(
        [sys.executable, "-m", "tm", "flow", "plan", str(flow_path), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["flows"][0]["issues"]
    codes = {issue["code"] for issue in payload["flows"][0]["issues"]}
    assert "max_depth_error" in codes
