"""Load governance configuration from ``trace-mind.toml``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

try:  # pragma: no cover - Python <3.11 fallback
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

LimitKey = Tuple[str, Optional[str], Optional[str]]


@dataclass(frozen=True)
class LimitSettings:
    enabled: bool = True
    qps: Optional[float] = None
    concurrency: Optional[int] = None
    tokens_per_min: Optional[float] = None
    cost_per_hour: Optional[float] = None

    def is_active(self) -> bool:
        return self.enabled and any(
            value is not None for value in (self.qps, self.concurrency, self.tokens_per_min, self.cost_per_hour)
        )


@dataclass(frozen=True)
class LimitsConfig:
    enabled: bool = False
    global_scope: LimitSettings = field(default_factory=LimitSettings)
    per_flow: Dict[str, LimitSettings] = field(default_factory=dict)
    per_policy_arm: Dict[Tuple[str, str], LimitSettings] = field(default_factory=dict)

    def any_limits(self) -> bool:
        if not self.enabled:
            return False
        if self.global_scope.is_active():
            return True
        if any(setting.is_active() for setting in self.per_flow.values()):
            return True
        if any(setting.is_active() for setting in self.per_policy_arm.values()):
            return True
        return False


@dataclass(frozen=True)
class BreakerSettings:
    enabled: bool = True
    window_sec: float = 30.0
    failure_threshold: int = 5
    timeout_threshold: int = 5
    cooldown_sec: float = 30.0
    half_open_max_calls: int = 1

    def is_active(self) -> bool:
        return self.enabled and (self.failure_threshold > 0 or self.timeout_threshold > 0)


@dataclass(frozen=True)
class BreakerConfig:
    enabled: bool = False
    global_scope: BreakerSettings = field(default_factory=BreakerSettings)
    per_flow: Dict[str, BreakerSettings] = field(default_factory=dict)
    per_policy: Dict[str, BreakerSettings] = field(default_factory=dict)

    def any_breakers(self) -> bool:
        if not self.enabled:
            return False
        if self.global_scope.is_active():
            return True
        if any(setting.is_active() for setting in self.per_flow.values()):
            return True
        if any(setting.is_active() for setting in self.per_policy.values()):
            return True
        return False


@dataclass(frozen=True)
class GovernanceConfig:
    enabled: bool = False
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    breaker: BreakerConfig = field(default_factory=BreakerConfig)
    guard: "GuardConfig" = field(default_factory=lambda: GuardConfig(enabled=False))
    hitl: "HitlConfig" = field(default_factory=lambda: HitlConfig(enabled=False))
    audit: "AuditConfig" = field(default_factory=lambda: AuditConfig(enabled=False))

    def limits_enabled(self) -> bool:
        return self.enabled and self.limits.any_limits()

    def breaker_enabled(self) -> bool:
        return self.enabled and self.breaker.any_breakers()

    def guard_enabled(self) -> bool:
        return self.enabled and self.guard.enabled and self.guard.has_rules()

    def hitl_enabled(self) -> bool:
        return self.enabled and self.hitl.enabled

    def audit_enabled(self) -> bool:
        return self.enabled and self.audit.enabled


def load_governance_config(path: str | Path | None = None) -> GovernanceConfig:
    config_path = Path(path) if path is not None else Path("trace-mind.toml")
    if not config_path.exists():
        return GovernanceConfig()
    try:
        with config_path.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception:
        return GovernanceConfig()

    g_section_raw = data.get("governance") if isinstance(data, Mapping) else None
    g_section = g_section_raw if isinstance(g_section_raw, Mapping) else data
    enabled = bool(_get_bool(g_section, "enabled", True))

    limits_section = _coalesce_sections(g_section, ("limits",))
    limits_enabled = bool(_get_bool(limits_section, "enabled", True)) and enabled
    limits = _parse_limits(limits_section, limits_enabled)

    breaker_section = _coalesce_sections(g_section, ("breaker", "circuit", "circuit_breaker"))
    breaker_enabled = bool(_get_bool(breaker_section, "enabled", True)) and enabled
    breaker = _parse_breakers(breaker_section, breaker_enabled)

    guard_section = _coalesce_sections(g_section, ("guard",))
    guard_enabled = bool(_get_bool(guard_section, "enabled", True)) and enabled
    guard = _parse_guard(guard_section, guard_enabled)

    hitl_section = _coalesce_sections(g_section, ("hitl", "approval"))
    hitl_enabled = bool(_get_bool(hitl_section, "enabled", True)) and enabled
    hitl = _parse_hitl(hitl_section, hitl_enabled)

    audit_section = _coalesce_sections(g_section, ("audit",))
    audit_enabled = bool(_get_bool(audit_section, "enabled", True)) and enabled
    audit = _parse_audit(audit_section, audit_enabled)

    return GovernanceConfig(
        enabled=enabled,
        limits=limits,
        breaker=breaker,
        guard=guard,
        hitl=hitl,
        audit=audit,
    )


def _coalesce_sections(data: Mapping[str, object], keys: Tuple[str, ...]) -> Mapping[str, object]:
    for key in keys:
        section = data.get(key)
        if isinstance(section, Mapping):
            return section
    return {}


def _as_rule_tuple(items: Iterable[Mapping[str, object]]) -> Tuple[Dict[str, object], ...]:
    result: list[Dict[str, object]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        entry = {str(k): v for k, v in item.items()}
        rule_type = entry.get("type")
        if isinstance(rule_type, str) and rule_type.strip():
            entry["type"] = rule_type.strip()
            result.append(entry)
    return tuple(result)


def _parse_limits(section: Mapping[str, object], enabled: bool) -> LimitsConfig:
    global_cfg = _parse_limit_settings(section.get("global")) if enabled else LimitSettings(enabled=False)

    flow_settings: Dict[str, LimitSettings] = {}
    flow_section = section.get("flow")
    if enabled and isinstance(flow_section, Mapping):
        for name, cfg in flow_section.items():
            settings = _parse_limit_settings(cfg)
            if settings.is_active():
                flow_settings[str(name)] = settings

    policy_settings: Dict[Tuple[str, str], LimitSettings] = {}
    policy_section = section.get("policy")
    if enabled and isinstance(policy_section, Mapping):
        for policy_name, policy_cfg in policy_section.items():
            if not isinstance(policy_cfg, Mapping):
                continue
            arm_section = policy_cfg.get("arm") if isinstance(policy_cfg.get("arm"), Mapping) else policy_cfg
            if not isinstance(arm_section, Mapping):
                continue
            for arm_name, arm_cfg in arm_section.items():
                settings = _parse_limit_settings(arm_cfg)
                if settings.is_active():
                    policy_settings[(str(policy_name), str(arm_name))] = settings

    return LimitsConfig(
        enabled=enabled,
        global_scope=global_cfg if global_cfg.is_active() else LimitSettings(enabled=False),
        per_flow=flow_settings,
        per_policy_arm=policy_settings,
    )


def _parse_limit_settings(raw) -> LimitSettings:  # type: ignore[no-untyped-def]
    if not isinstance(raw, Mapping):
        return LimitSettings(enabled=False)
    return LimitSettings(
        enabled=bool(_get_bool(raw, "enabled", True)),
        qps=_get_float(raw, "qps"),
        concurrency=_get_int(raw, "concurrency"),
        tokens_per_min=_get_float(raw, "tokens_per_min"),
        cost_per_hour=_get_float(raw, "cost_per_hour"),
    )


def _parse_breakers(section: Mapping[str, object], enabled: bool) -> BreakerConfig:
    global_cfg = _parse_breaker_settings(section.get("global")) if enabled else BreakerSettings(enabled=False)

    flow_settings: Dict[str, BreakerSettings] = {}
    flow_section = section.get("flow")
    if enabled and isinstance(flow_section, Mapping):
        for name, cfg in flow_section.items():
            settings = _parse_breaker_settings(cfg)
            if settings.is_active():
                flow_settings[str(name)] = settings

    policy_settings: Dict[str, BreakerSettings] = {}
    policy_section = section.get("policy")
    if enabled and isinstance(policy_section, Mapping):
        for policy_name, cfg in policy_section.items():
            settings = _parse_breaker_settings(cfg)
            if settings.is_active():
                policy_settings[str(policy_name)] = settings

    return BreakerConfig(
        enabled=enabled,
        global_scope=global_cfg if global_cfg.is_active() else BreakerSettings(enabled=False),
        per_flow=flow_settings,
        per_policy=policy_settings,
    )


def _parse_breaker_settings(raw) -> BreakerSettings:  # type: ignore[no-untyped-def]
    if not isinstance(raw, Mapping):
        return BreakerSettings(enabled=False)
    return BreakerSettings(
        enabled=bool(_get_bool(raw, "enabled", True)),
        window_sec=_get_float(raw, "window_sec", default=30.0) or 30.0,
        failure_threshold=_get_int(raw, "failure_threshold", default=5) or 0,
        timeout_threshold=_get_int(raw, "timeout_threshold", default=5) or 0,
        cooldown_sec=_get_float(raw, "cooldown_sec", default=30.0) or 0.0,
        half_open_max_calls=_get_int(raw, "half_open_max_calls", default=1) or 1,
    )


def _get_bool(section: Mapping[str, object], key: str, default: bool) -> bool:
    value = section.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _get_int(section: Mapping[str, object], key: str, *, default: int | None = None) -> Optional[int]:
    value = section.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class GuardConfig:
    enabled: bool = False
    global_rules: Tuple[Dict[str, object], ...] = field(default_factory=tuple)
    flow_rules: Dict[str, Tuple[Dict[str, object], ...]] = field(default_factory=dict)
    policy_rules: Dict[str, Tuple[Dict[str, object], ...]] = field(default_factory=dict)

    def has_rules(self) -> bool:
        return bool(self.global_rules or self.flow_rules or self.policy_rules)


def _parse_guard(section: Mapping[str, object], enabled: bool) -> GuardConfig:
    if not enabled:
        return GuardConfig(enabled=False)

    global_rules: list[Dict[str, object]] = []
    flow_rules: Dict[str, list[Dict[str, object]]] = {}
    policy_rules: Dict[str, list[Dict[str, object]]] = {}

    def _consume_rules(scope: str, target: Optional[str], rules_obj) -> None:
        rule_list = _rules_from_obj(rules_obj)
        if not rule_list:
            return
        if scope == "global":
            global_rules.extend(rule_list)
        elif scope == "flow" and target:
            flow_rules.setdefault(str(target), []).extend(rule_list)
        elif scope == "policy" and target:
            policy_rules.setdefault(str(target), []).extend(rule_list)

    # support [[guard.rules]] blocks
    rule_blocks = section.get("rules")
    if isinstance(rule_blocks, Sequence) and not isinstance(rule_blocks, (str, bytes)):
        for block in rule_blocks:
            if not isinstance(block, Mapping):
                continue
            scope = str(block.get("scope", "global") or "global").strip().lower()
            target = block.get("target")
            _consume_rules(scope, target if isinstance(target, str) else None, block.get("rules", block))

    # support guard.global.rules
    global_section = section.get("global")
    if isinstance(global_section, Mapping):
        _consume_rules("global", None, global_section.get("rules", global_section))

    flow_section = section.get("flow")
    if isinstance(flow_section, Mapping):
        for name, cfg in flow_section.items():
            _consume_rules("flow", str(name), cfg)

    policy_section = section.get("policy")
    if isinstance(policy_section, Mapping):
        for name, cfg in policy_section.items():
            _consume_rules("policy", str(name), cfg)

    return GuardConfig(
        enabled=True,
        global_rules=_as_rule_tuple(global_rules),
        flow_rules={k: _as_rule_tuple(v) for k, v in flow_rules.items()},
        policy_rules={k: _as_rule_tuple(v) for k, v in policy_rules.items()},
    )


def _rules_from_obj(raw) -> Tuple[Dict[str, object], ...]:  # type: ignore[no-untyped-def]
    if isinstance(raw, Mapping) and "type" in raw:
        return _as_rule_tuple([raw])
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        mappings = [entry for entry in raw if isinstance(entry, Mapping)]
        return _as_rule_tuple(mappings)
    return tuple()


@dataclass(frozen=True)
class HitlConfig:
    enabled: bool = False
    default_ttl_ms: int = 600_000
    persistence_path: Optional[str] = None
    queue_size: int = 0


def _parse_hitl(section: Mapping[str, object], enabled: bool) -> HitlConfig:
    if not enabled:
        return HitlConfig(enabled=False)
    return HitlConfig(
        enabled=True,
        default_ttl_ms=_get_int(section, "default_ttl_ms", default=600_000) or 600_000,
        persistence_path=str(section.get("persistence")) if isinstance(section.get("persistence"), str) else None,
        queue_size=_get_int(section, "queue_size", default=0) or 0,
    )


@dataclass(frozen=True)
class AuditConfig:
    enabled: bool = False
    path: str = "data/audit.jsonl"
    mask_fields: Tuple[str, ...] = ("input", "output")


def _parse_audit(section: Mapping[str, object], enabled: bool) -> AuditConfig:
    if not enabled:
        return AuditConfig(enabled=False)
    path_value = section.get("path")
    mask_value = section.get("mask_fields")
    masks: Tuple[str, ...]
    if isinstance(mask_value, Sequence) and not isinstance(mask_value, (str, bytes)) and mask_value:
        masks = tuple(str(entry) for entry in mask_value if isinstance(entry, str))
    else:
        masks = ("input", "output")
    return AuditConfig(
        enabled=True,
        path=str(path_value) if isinstance(path_value, str) and path_value else "data/audit.jsonl",
        mask_fields=masks,
    )


def _get_float(section: Mapping[str, object], key: str, *, default: float | None = None) -> Optional[float]:
    value = section.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "LimitKey",
    "LimitSettings",
    "LimitsConfig",
    "BreakerSettings",
    "BreakerConfig",
    "GovernanceConfig",
    "load_governance_config",
    "GuardConfig",
    "HitlConfig",
    "AuditConfig",
]
