from __future__ import annotations

from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Mapping, Optional

try:  # pragma: no cover - python < 3.11 fallback
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass(frozen=True)
class RewardWeights:
    outcome_ok: float = 0.5
    latency_ms: float = -0.2
    cost_usd: float = -0.2
    user_rating: float = 0.3
    task_success: float = 0.4

    def with_overrides(self, overrides: Mapping[str, object]) -> "RewardWeights":
        updates: dict[str, float] = {}
        for field in fields(self):
            raw = overrides.get(field.name)
            if raw is None:
                continue
            try:
                updates[field.name] = float(raw)
            except (TypeError, ValueError):
                continue
        if not updates:
            return self
        return replace(self, **updates)


def default_reward_weights() -> RewardWeights:
    return RewardWeights()


def load_reward_weights(
    config_path: Path | str | None = None,
    *,
    defaults: Optional[RewardWeights] = None,
) -> RewardWeights:
    base = defaults or default_reward_weights()
    path = Path(config_path) if config_path is not None else Path("trace-mind.toml")
    if not path.exists():
        return base
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception:
        return base
    section = data.get("reward_weights")
    if not isinstance(section, Mapping):
        return base
    return base.with_overrides(section)


__all__ = ["RewardWeights", "default_reward_weights", "load_reward_weights"]
