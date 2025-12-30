from __future__ import annotations

from typing import Any, Mapping

from tm.agents.models import AgentSpec
from tm.agents.registry import AgentRegistryError, register_agent
from tm.agents.runtime import RuntimeAgent
from tm.controllers.builtins.act_mock import ActMockAgent
from tm.controllers.builtins.decide_llm_stub import DecideLLMStubAgent
from tm.controllers.builtins.observe_mock import ObserveMockAgent

__all__ = [
    "ActMockAgent",
    "DecideLLMStubAgent",
    "ObserveMockAgent",
]


def _register_agent(agent_cls: type[RuntimeAgent]) -> None:
    def factory(spec: AgentSpec, config: Mapping[str, Any]) -> RuntimeAgent:
        return agent_cls(spec, config)

    try:
        register_agent(agent_cls.AGENT_ID, factory)
    except AgentRegistryError:
        pass


for _agent_cls in (ObserveMockAgent, DecideLLMStubAgent, ActMockAgent):
    _register_agent(_agent_cls)
