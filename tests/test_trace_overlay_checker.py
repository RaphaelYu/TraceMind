from scripts.trace_overlay_checker import analyze


def test_overlay_reports_anomalies():
    artifacts = {
        "demo": {
            "rev-2": {
                "step_ids": {"step-a", "step-b"},
                "names": {"a", "b"},
            }
        }
    }

    runs = {
        "run1": [
            {"flow": "demo", "flow_rev": "rev-2", "step": "a", "step_id": "step-a", "seq": 0},
            {"flow": "demo", "flow_rev": "rev-2", "step": "b", "step_id": "step-b", "seq": 1},
        ],
        "run2": [
            {"flow": "demo", "flow_rev": "rev-2", "step": "c", "step_id": "step-c", "seq": 0},
        ],
        "run3": [
            {"flow": "demo", "flow_rev": "rev-999", "step": "a", "seq": 0},
        ],
        "run4": [
            {"flow": "demo", "flow_rev": "rev-2", "step": "c", "step_id": "step-a", "seq": 0},
        ],
    }

    report = analyze(runs, artifacts)
    assert report["runs_analyzed"] == 4
    assert report["events"] == 5
    assert len(report["anomalies"]) == 3
    reasons = {a["reason"] for a in report["anomalies"]}
    assert reasons == {"STEP_ID_NOT_FOUND", "REV_NOT_FOUND", "STEP_NAME_MISMATCH"}
