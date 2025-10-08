"""Minimal client/server helpers for MCP (Model Context Protocol) style JSON-RPC."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict
from urllib import request, error


@dataclass
class McpClient:
    base_url: str

    def call(self, tool: str, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "method": f"{tool}.{method}",
            "params": params,
            "id": 1,
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.base_url,
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with request.urlopen(req) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                body = resp.read().decode(charset)
        except error.HTTPError as exc:
            raise RuntimeError(f"MCP call failed: {exc.code} {exc.reason}") from exc
        result = json.loads(body)
        if "error" in result:
            raise RuntimeError(f"MCP error: {result['error']}")
        return result.get("result", {})


@dataclass
class McpServer:
    tools: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def register_tool(self, tool: Dict[str, Any]) -> None:
        name = tool.get("name")
        if not name:
            raise ValueError("Tool definition must include a 'name'")
        self.tools[name] = tool

    def handle(self, jsonrpc_request: Dict[str, Any]) -> Dict[str, Any]:
        method = jsonrpc_request.get("method", "")
        request_id = jsonrpc_request.get("id")
        params = jsonrpc_request.get("params", {})

        if "." not in method:
            return self._error_response(request_id, f"Malformed method '{method}'")

        tool_name, action = method.split(".", 1)
        tool = self.tools.get(tool_name)
        if not tool:
            return self._error_response(request_id, f"Unknown tool '{tool_name}'")

        handler: Callable[[str, Dict[str, Any]], Any] | None = tool.get("handler")  # type: ignore[assignment]
        if callable(handler):
            try:
                result = handler(action, params)
            except Exception as exc:  # pragma: no cover - defensive guard
                return self._error_response(request_id, str(exc))
        else:
            # default echo behaviour
            result = {"tool": tool_name, "action": action, "params": params}

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }

    @staticmethod
    def _error_response(request_id: Any, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32000, "message": message},
        }
