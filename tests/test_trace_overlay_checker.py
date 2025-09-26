import json
import tempfile
from pathlib import Path

from scripts.trace_overlay_checker import analyze


def test_overlay_reports_anomalies():
    artifacts = {
        "demo": {
            "rev-2": {"a", "b"}
        }
    }

    runs = {
        "run1": [
            {"flow": "demo", "flow_rev": "rev-2", "step": "a", "seq": 0},
            {"flow": "demo", "flow_rev": "rev-2", "step": "b", "seq": 1},
        ],
        "run2": [
            {"flow": "demo", "flow_rev": "rev-2", "step": "c", "seq": 0},
        ],
        "run3": [
            {"flow": "demo", "flow_rev": "rev-999", "step": "a", "seq": 0},
        ],
    }

    report = analyze(runs, artifacts)
    assert report["runs_analyzed"] == 3
    assert report["events"] == 4
    assert len(report["anomalies"]) == 2
    reasons = {a["reason"] for a in report["anomalies"]}
    assert reasons == {"STEP_NOT_FOUND", "REV_NOT_FOUND"}
