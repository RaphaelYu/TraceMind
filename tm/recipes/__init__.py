"""FlowSpec-based recipes for common connector-driven workflows."""

from .k8s_flows import pod_health_check, restart_crashloop
from .docker_flows import container_health, restart_container
from .mcp_flows import mcp_tool_call

__all__ = [
    "pod_health_check",
    "restart_crashloop",
    "container_health",
    "restart_container",
    "mcp_tool_call",
]
