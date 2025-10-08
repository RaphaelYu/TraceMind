from __future__ import annotations
import asyncio
from typing import Any, Dict, Mapping, Callable


class InProcessTransport:
    """Test/dummy transport that dispatches to an in-process handler function.

    handler(payload) -> response dict
    """

    def __init__(self, handler: Callable[[Mapping[str, Any]], Dict[str, Any]]):
        self._h = handler

    async def request(self, payload: Mapping[str, Any], *, timeout_s: float | None = None) -> Dict[str, Any]:
        # simulate async
        await asyncio.sleep(0)
        return self._h(payload)
