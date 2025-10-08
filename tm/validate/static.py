from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Dict, Iterable, Mapping, Sequence, cast


@dataclass(frozen=True)
class Conflict:
    kind: str
    detail: str
    subjects: Sequence[str]


@dataclass(frozen=True)
class _NumericRange:
    lower: float
    lower_inclusive: bool
    upper: float
    upper_inclusive: bool


@dataclass(frozen=True)
class _FieldCondition:
    expr: str
    numeric: _NumericRange | None


def _collect(ids: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in ids:
        counts[item] = counts.get(item, 0) + 1
    return counts


def find_conflicts(
    flows: Sequence[Mapping[str, object]], policies: Sequence[Mapping[str, object]]
) -> Sequence[Conflict]:
    conflicts: list[Conflict] = []

    flow_ids = _collect(str(flow.get("id", "")) for flow in flows)
    for fid, count in flow_ids.items():
        if not fid:
            conflicts.append(Conflict(kind="flow.missing_id", detail="flow missing id", subjects=[fid]))
        if count > 1:
            conflicts.append(Conflict(kind="flow.id_collision", detail=f"flow id '{fid}' repeated", subjects=[fid]))

    policy_ids = _collect(str(policy.get("policy_id", "")) for policy in policies)
    for pid, count in policy_ids.items():
        if not pid:
            conflicts.append(Conflict(kind="policy.missing_id", detail="policy missing policy_id", subjects=[pid]))
        if count > 1:
            conflicts.append(Conflict(kind="policy.id_collision", detail=f"policy id '{pid}' repeated", subjects=[pid]))

    lock_usage: Dict[str, Dict[str, set[str]]] = {}
    cron_usage: Dict[str, set[str]] = {}

    for flow in flows:
        fid = str(flow.get("id", "")) or "<unknown>"
        env = flow.get("env")
        if env is not None:
            if not isinstance(env, Mapping):
                conflicts.append(
                    Conflict(
                        kind="flow.env_invalid",
                        detail=f"flow '{fid}' env must be mapping",
                        subjects=[fid],
                    )
                )
            else:
                for key, value in env.items():
                    if not isinstance(key, str) or not isinstance(value, (str, int, float, bool)):
                        conflicts.append(
                            Conflict(
                                kind="flow.env_invalid",
                                detail=f"flow '{fid}' has non-scalar env value for '{key}'",
                                subjects=[fid, str(key)],
                            )
                        )

        schedule = flow.get("schedule")
        if isinstance(schedule, Mapping):
            cron_expr = schedule.get("cron")
            if isinstance(cron_expr, str) and cron_expr.strip():
                cron_usage.setdefault(cron_expr.strip(), set()).add(fid)

        steps = flow.get("steps")
        if not isinstance(steps, Mapping):
            continue
        for spec in steps.values():
            if not isinstance(spec, Mapping):
                continue
            locks = spec.get("locks")
            if not isinstance(locks, Iterable):
                continue
            for entry in locks:
                if not isinstance(entry, Mapping):
                    continue
                name = str(entry.get("name", ""))
                if not name:
                    conflicts.append(
                        Conflict(
                            kind="flow.lock_invalid",
                            detail=f"flow '{fid}' has lock without name",
                            subjects=[fid],
                        )
                    )
                    continue
                mode = str(entry.get("mode", "exclusive")).lower()
                if mode not in {"exclusive", "shared"}:
                    conflicts.append(
                        Conflict(
                            kind="flow.lock_invalid",
                            detail=f"flow '{fid}' lock '{name}' has invalid mode '{mode}'",
                            subjects=[fid, name],
                        )
                    )
                    mode = "exclusive"
                slot = lock_usage.setdefault(name, {"exclusive": set(), "shared": set()})
                slot[mode].add(fid)

    for name, slot in lock_usage.items():
        exclusives = slot.get("exclusive", set())
        shareds = slot.get("shared", set())
        if len(exclusives) > 1:
            conflicts.append(
                Conflict(
                    kind="flow.lock_conflict",
                    detail=f"lock '{name}' exclusive in flows {sorted(exclusives)}",
                    subjects=tuple(sorted(exclusives)),
                )
            )
        if exclusives and shareds:
            subjects = tuple(sorted(exclusives | shareds))
            conflicts.append(
                Conflict(
                    kind="flow.lock_conflict",
                    detail=f"lock '{name}' exclusive/shared mix across flows",
                    subjects=subjects,
                )
            )

    for cron_expr, flows_with_cron in cron_usage.items():
        if len(flows_with_cron) > 1:
            conflicts.append(
                Conflict(
                    kind="flow.cron_overlap",
                    detail=f"cron '{cron_expr}' shared by flows {sorted(flows_with_cron)}",
                    subjects=tuple(sorted(flows_with_cron)),
                )
            )

    for policy in policies:
        pid = str(policy.get("policy_id", "")) or "<unknown>"
        arms_raw = policy.get("arms")
        arm_entries: list[Mapping[str, object]] = []
        if isinstance(arms_raw, Iterable) and not isinstance(arms_raw, (str, bytes)):
            for entry in arms_raw:
                if isinstance(entry, Mapping):
                    arm_entries.append(entry)
        normalized: list[tuple[str, Dict[str, _FieldCondition]]] = []
        for arm in arm_entries:
            name = str(arm.get("name", "")) or "<unnamed>"
            condition_data = arm.get("if", {})
            mapping_condition = (
                cast(Mapping[str, object], condition_data) if isinstance(condition_data, Mapping) else {}
            )
            normalized.append((name, _normalize_condition(mapping_condition)))

        for idx in range(len(normalized)):
            name_a, cond_a = normalized[idx]
            for jdx in range(idx + 1, len(normalized)):
                name_b, cond_b = normalized[jdx]
                if _conditions_overlap(cond_a, cond_b):
                    conflicts.append(
                        Conflict(
                            kind="policy.arm_overlap",
                            detail=f"policy '{pid}' arms '{name_a}' and '{name_b}' overlap",
                            subjects=[pid, name_a, name_b],
                        )
                    )

    return conflicts


def _normalize_condition(condition: Mapping[str, object]) -> Dict[str, _FieldCondition]:
    result: Dict[str, _FieldCondition] = {}
    for raw_key, raw_expr in condition.items():
        key = str(raw_key)
        expr = str(raw_expr)
        numeric = _parse_numeric_expr(expr)
        result[key] = _FieldCondition(expr=expr, numeric=numeric)
    return result


def _parse_numeric_expr(expr: str) -> _NumericRange | None:
    text = expr.strip()
    operators = ["<=", ">=", "<", ">", "==", "="]
    for op in operators:
        if text.startswith(op):
            try:
                value = float(text[len(op) :].strip())
            except ValueError:
                return None
            if op == "<":
                return _NumericRange(lower=-inf, lower_inclusive=False, upper=value, upper_inclusive=False)
            if op == "<=":
                return _NumericRange(lower=-inf, lower_inclusive=False, upper=value, upper_inclusive=True)
            if op == ">":
                return _NumericRange(lower=value, lower_inclusive=False, upper=inf, upper_inclusive=False)
            if op == ">=":
                return _NumericRange(lower=value, lower_inclusive=True, upper=inf, upper_inclusive=False)
            if op in {"=", "=="}:
                return _NumericRange(lower=value, lower_inclusive=True, upper=value, upper_inclusive=True)
    try:
        value = float(text)
    except ValueError:
        return None
    return _NumericRange(lower=value, lower_inclusive=True, upper=value, upper_inclusive=True)


def _conditions_overlap(a: Dict[str, _FieldCondition], b: Dict[str, _FieldCondition]) -> bool:
    shared = set(a.keys()) & set(b.keys())
    if not shared:
        return False
    for field in shared:
        cond_a = a[field]
        cond_b = b[field]
        range_a = cond_a.numeric
        range_b = cond_b.numeric
        if range_a and range_b:
            if _ranges_overlap(range_a, range_b):
                return True
        elif cond_a.expr == cond_b.expr:
            return True
    return False


def _ranges_overlap(a: _NumericRange, b: _NumericRange) -> bool:
    if a.lower > b.lower:
        lower = a.lower
        lower_inc = a.lower_inclusive
    elif a.lower < b.lower:
        lower = b.lower
        lower_inc = b.lower_inclusive
    else:
        lower = a.lower
        lower_inc = a.lower_inclusive and b.lower_inclusive

    if a.upper < b.upper:
        upper = a.upper
        upper_inc = a.upper_inclusive
    elif a.upper > b.upper:
        upper = b.upper
        upper_inc = b.upper_inclusive
    else:
        upper = a.upper
        upper_inc = a.upper_inclusive and b.upper_inclusive

    if lower < upper:
        return True
    if lower == upper:
        return lower_inc and upper_inc
    return False
