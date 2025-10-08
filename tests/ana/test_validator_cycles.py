from __future__ import annotations

from tm.ana.validator import IssueLevel, validate


def _codes(report):
    return [issue.code for issue in report.issues]


def test_validator_accepts_linear_flow():
    report = validate({"start": ["middle"], "middle": ["end"], "end": []})
    assert report.issues == ()
    assert report.has_errors() is False


def test_validator_detects_cycle():
    report = validate({"a": ["b"], "b": ["a"]})
    assert report.has_errors() is True
    assert "cycle_detected" in _codes(report)
    assert any(issue.code == "no_entrypoint" for issue in report.issues)


def test_validator_flags_unknown_target():
    report = validate({"start": ["unknown"]})
    assert "unknown_target" in _codes(report)
    assert report.has_errors() is True


def test_validator_reports_duplicate_edges():
    report = validate({"root": ["leaf", "leaf"]})
    assert any(issue.code == "duplicate_edge" and issue.level == IssueLevel.WARNING for issue in report.issues)


def test_validator_rejects_invalid_identifier():
    report = validate({"bad id": []})
    assert any(issue.code == "invalid_id" for issue in report.issues)


def test_validator_finds_unreachable_nodes():
    graph = {
        "entry": ["a"],
        "a": ["b"],
        "b": [],
        # disconnected component
        "orphan": ["leaf"],
        "leaf": [],
    }
    report = validate(graph)
    assert report.has_errors() is True
    assert "unreachable_node" in _codes(report)
    assert any(issue.node == "orphan" for issue in report.issues if issue.code == "unreachable_node")
    assert any(issue.code == "extra_entrypoint" and issue.node == "orphan" for issue in report.issues)
