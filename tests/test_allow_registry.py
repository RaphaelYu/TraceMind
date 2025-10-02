import pytest

from tm.ai.registry import (
    PolicyForbiddenError,
    flow_allow_registry,
    reset_audit_log,
    reset_registries,
    tool_registry,
    audit_log,
)


def dummy_handler():
    return "ok"


def setup_function(function):
    reset_registries()


def test_tool_registry_allows_registered_tool():
    tool_registry.register("tool.sort", dummy_handler)
    tool_registry.allow(["tool.sort"])
    assert tool_registry.is_allowed("tool.sort")
    tool_registry.require_allowed("tool.sort", reason="planning")


def test_tool_registry_rejects_unallowed_tool_and_audits():
    tool_registry.register("tool.analyse", dummy_handler)
    with pytest.raises(PolicyForbiddenError) as exc:
        tool_registry.require_allowed("tool.analyse", reason="execute")
    assert exc.value.ref == "tool.analyse"
    violations = audit_log()
    assert violations
    latest = violations[-1]
    assert latest["kind"] == "tool"
    assert latest["ref"] == "tool.analyse"
    assert latest["reason"] == "execute"


def test_flow_allow_registry_blocks_disallowed_flow():
    flow_allow_registry.allow(["flow.alpha"])
    flow_allow_registry.require_allowed("flow.alpha", reason="plan")
    with pytest.raises(PolicyForbiddenError):
        flow_allow_registry.require_allowed("flow.beta", reason="plan")


def test_register_duplicate_tool_rejected():
    tool_registry.register("tool.unique", dummy_handler)
    with pytest.raises(ValueError):
        tool_registry.register("tool.unique", dummy_handler)
