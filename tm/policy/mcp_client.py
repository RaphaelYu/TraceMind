from __future__ import annotations
import itertools
from typing import Any, Dict, Optional, Protocol, Mapping


class MCPTransport(Protocol):
    async def request(self, payload: Mapping[str, Any], *, timeout_s: float | None = None) -> Dict[str, Any]: ...


class JSONRPCError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.data = data


class MCPClient:
    """Minimal JSON-RPC 2.0 client for MCP policy endpoint.
    Transport is pluggable (e.g., websockets/aiohttp/tcp/stdio).
    """

    def __init__(self, transport: MCPTransport):
        self._t = transport
        self._seq = itertools.count(1)

    async def call(
        self, method: str, params: Optional[Dict[str, Any]] = None, *, timeout_s: float | None = None
    ) -> Any:
        req = {"jsonrpc": "2.0", "id": next(self._seq), "method": method}
        if params is not None:
            req["params"] = params
        resp = await self._t.request(req, timeout_s=timeout_s)
        if "error" in resp:
            err = resp["error"]
            raise JSONRPCError(err.get("code", -1), err.get("message", "error"), err.get("data"))
        return resp.get("result")
