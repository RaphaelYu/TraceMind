from typing import Any, Mapping

from tm.agents.models import AgentSpec
from tm.agents.registry import AgentRegistryError, register_agent
from tm.agents.runtime import RuntimeAgent
from tm.agents.builtins.http_mock import HttpMockAgent
from tm.agents.builtins.noop import NoopAgent
from tm.agents.builtins.shell import ShellAgent
from tm.connectors.http_agent import HttpConnectorAgent

__all__ = [
    "AgentRegistryError",
    "register_agent",
    "HttpMockAgent",
    "NoopAgent",
    "ShellAgent",
]


def _register_agent(agent_cls: type[RuntimeAgent]) -> None:
    def factory(spec: AgentSpec, config: Mapping[str, Any]) -> RuntimeAgent:
        return agent_cls(spec, config)

    try:
        register_agent(agent_cls.AGENT_ID, factory)
    except AgentRegistryError:
        pass


for _agent_cls in (NoopAgent, ShellAgent, HttpMockAgent, HttpConnectorAgent):
    _register_agent(_agent_cls)
