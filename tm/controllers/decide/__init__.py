from __future__ import annotations

from typing import Mapping

from tm.agents.models import AgentSpec
from tm.agents.registry import AgentRegistryError, register_agent
from tm.agents.runtime import RuntimeAgent

from .decide_agent import DecideAgent

__all__ = ["DecideAgent"]


def _register_agent(agent_cls: type[RuntimeAgent]) -> None:
    def factory(spec: AgentSpec, config: Mapping[str, object]) -> RuntimeAgent:
        return agent_cls(spec, config)

    try:
        register_agent(agent_cls.AGENT_ID, factory)
    except AgentRegistryError:
        pass


_register_agent(DecideAgent)
