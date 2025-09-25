from typing import Optional, Dict, Any

class DecisionHook:
    def before_route(self, ctx: dict, policy: dict) -> Optional[dict]:
        # Example: allow per-model overrides
        return None
    def after_result(self, ctx: dict, result: dict) -> None:
        pass
