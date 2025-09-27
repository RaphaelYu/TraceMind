from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional

try:
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional
    yaml = None  # type: ignore

from .tuner import BanditTuner


class PolicyError(ValueError):
    """Raised when a policy recipe cannot be parsed or registered."""


@dataclass
class PolicyDefinition:
    policy_id: str
    strategy: str
    params: Dict[str, object]
    arms: Optional[Iterable[str]] = None
    endpoint: Optional[str] = None


class PolicyRegistry:
    def __init__(self) -> None:
        self._policies: Dict[str, PolicyDefinition] = {}

    def register(self, definition: PolicyDefinition) -> None:
        if definition.policy_id in self._policies:
            raise PolicyError(f"Policy '{definition.policy_id}' already registered")
        self._policies[definition.policy_id] = definition

    def get(self, policy_id: str) -> PolicyDefinition:
        try:
            return self._policies[policy_id]
        except KeyError as exc:
            raise PolicyError(f"Unknown policy '{policy_id}'") from exc

    def all(self) -> Mapping[str, PolicyDefinition]:
        return dict(self._policies)


policy_registry = PolicyRegistry()


class PolicyLoader:
    """Load policy recipes from JSON/YAML text or files."""

    def load(self, source: str | Path) -> PolicyDefinition:
        data = self._read_source(source)
        recipe = data.get("policy")
        if not isinstance(recipe, dict):
            raise PolicyError("Recipe missing 'policy' object")

        policy_id = self._expect_str(recipe, "id")
        strategy = recipe.get("strategy", "epsilon")
        if not isinstance(strategy, str) or not strategy:
            raise PolicyError("policy.strategy must be a non-empty string")

        params = recipe.get("params", {})
        if not isinstance(params, dict):
            raise PolicyError("policy.params must be an object")

        arms = recipe.get("arms")
        if arms is not None:
            if not isinstance(arms, list) or not all(isinstance(arm, str) for arm in arms):
                raise PolicyError("policy.arms must be a list of strings")
        endpoint = recipe.get("endpoint")
        if endpoint is not None and not isinstance(endpoint, str):
            raise PolicyError("policy.endpoint must be a string")

        definition = PolicyDefinition(
            policy_id=policy_id,
            strategy=strategy,
            params=params,
            arms=list(arms) if arms else None,
            endpoint=endpoint,
        )
        policy_registry.register(definition)
        return definition

    def _read_source(self, source: str | Path) -> Dict[str, object]:
        if isinstance(source, Path) or (isinstance(source, str) and Path(source).exists()):
            path = Path(source)
            text = path.read_text(encoding="utf-8")
            hint = path.suffix.lower()
            return self._parse_text(text, hint)
        if isinstance(source, str):
            return self._parse_text(source, None)
        raise PolicyError("Unsupported policy source")

    def _parse_text(self, text: str, hint: Optional[str]) -> Dict[str, object]:
        order = []
        if hint in {".json"}:
            order = ["json", "yaml"]
        elif hint in {".yml", ".yaml"}:
            order = ["yaml", "json"]
        else:
            order = ["json", "yaml"]

        last_exc: Optional[Exception] = None
        for kind in order:
            if kind == "json":
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as exc:
                    last_exc = exc
                else:
                    if isinstance(data, dict):
                        return data
                    last_exc = PolicyError("JSON policy must decode to an object")
            elif kind == "yaml" and yaml is not None:
                try:
                    data = yaml.safe_load(text)
                except Exception as exc:  # pragma: no cover
                    last_exc = exc
                else:
                    if isinstance(data, dict):
                        return data
                    last_exc = PolicyError("YAML policy must decode to an object")
        raise PolicyError(f"Failed to parse policy recipe: {last_exc}")

    def _expect_str(self, obj: Dict[str, object], key: str) -> str:
        value = obj.get(key)
        if not isinstance(value, str) or not value:
            raise PolicyError(f"Field '{key}' must be a non-empty string")
        return value


async def apply_policy(tuner: BanditTuner, policy_id: str) -> None:
    definition = policy_registry.get(policy_id)
    await tuner.configure(policy_id, definition.params, version=definition.strategy, source="policy")


__all__ = ["PolicyRegistry", "policy_registry", "PolicyLoader", "PolicyDefinition", "PolicyError", "apply_policy"]
