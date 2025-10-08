from __future__ import annotations
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from tm.policy.local_store import LocalPolicyStore
from tm.policy.mcp_client import MCPClient, JSONRPCError
from tm.utils.async_tools import with_timeout


@dataclass
class PolicyAdapter:
    """MCP-backed policy adapter with graceful fallback to LocalPolicyStore.

    Methods:
      - get(arm) -> params | None
      - update(arm, params) -> params
      - list_arms() -> list[str]

    Logs/metrics are intentionally omitted here to keep zero-conflict.
    """

    mcp: Optional[MCPClient]
    local: LocalPolicyStore
    timeout_s: float = 5.0
    prefer_remote: bool = True  # try MCP first if available

    async def _remote_get(self, arm: str) -> Optional[Dict[str, Any]]:
        assert self.mcp is not None
        try:
            res = await with_timeout(self.mcp.call("policy.get", {"arm": arm}), self.timeout_s)
            return res  # may be None
        except (JSONRPCError, Exception):
            return None

    async def _remote_update(self, arm: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        assert self.mcp is not None
        try:
            res = await with_timeout(self.mcp.call("policy.update", {"arm": arm, "params": params}), self.timeout_s)
            return res
        except (JSONRPCError, Exception):
            return None

    async def _remote_list(self) -> Optional[List[str]]:
        assert self.mcp is not None
        try:
            res = await with_timeout(self.mcp.call("policy.list_arms", {}), self.timeout_s)
            return list(res or [])
        except (JSONRPCError, Exception):
            return None

    async def get(self, arm: str) -> Optional[Dict[str, Any]]:
        if self.prefer_remote and self.mcp is not None:
            res = await self._remote_get(arm)
            if res is not None:
                return res
        # fallback
        return await self.local.get(arm)

    async def update(self, arm: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if self.prefer_remote and self.mcp is not None:
            res = await self._remote_update(arm, params)
            if res is not None:
                # optimistic sync local
                await self.local.update(arm, res)
                return res
        # fallback local update
        return await self.local.update(arm, params)

    async def list_arms(self) -> List[str]:
        if self.prefer_remote and self.mcp is not None:
            res = await self._remote_list()
            if res is not None:
                return res
        return await self.local.list_arms()
