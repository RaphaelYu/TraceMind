from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List


@dataclass
class LocalPolicyStore:
    """Simple in-memory policy store used as fallback.
    Thread-safe concerns are delegated to the caller/async context.
    """

    arms: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    version: str = "local:0"

    async def get(self, arm: str) -> Optional[Dict[str, Any]]:
        return self.arms.get(arm)

    async def update(self, arm: str, params: Dict[str, Any]) -> Dict[str, Any]:
        cur = self.arms.get(arm, {}).copy()
        cur.update(params)
        self.arms[arm] = cur
        # bump version (simple counter suffix)
        prefix, _, n = self.version.partition(":")
        try:
            self.version = f"{prefix}:{int(n or '0') + 1}"
        except Exception:
            self.version = "local:1"
        return cur

    async def list_arms(self) -> List[str]:
        return sorted(self.arms.keys())

    async def snapshot(self) -> Dict[str, Any]:
        return {"version": self.version, "arms": self.arms.copy()}
