from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from tm.ai.feedback import FeedbackEvent, reward
from tm.ai.reward_config import load_reward_weights


@dataclass
class _Run:
    binding: str
    arm: str
    status: str
    outcome: str
    duration_ms: float
    cost_usd: float
    user_rating: Optional[float]
    end_ts: float
    reward_value: float
    meta: Dict[str, object]


@dataclass
class _Metrics:
    n: int = 0
    ok: int = 0
    reward_sum: float = 0.0
    latency_sum: float = 0.0
    cost_sum: float = 0.0

    def add(self, run: _Run) -> None:
        self.n += 1
        if run.status.lower() == "ok":
            self.ok += 1
        self.reward_sum += run.reward_value
        self.latency_sum += run.duration_ms
        self.cost_sum += run.cost_usd

    def as_dict(self) -> Dict[str, float]:
        if self.n == 0:
            return {"n": 0, "ok_rate": 0.0, "avg_latency_ms": 0.0, "avg_cost_usd": 0.0, "avg_reward": 0.0}
        return {
            "n": self.n,
            "ok_rate": self.ok / self.n,
            "avg_latency_ms": self.latency_sum / self.n,
            "avg_cost_usd": self.cost_sum / self.n,
            "avg_reward": self.reward_sum / self.n,
        }


def _parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline evaluation over historical run records")
    parser.add_argument("--from-jsonl", dest="from_jsonl", type=Path, required=True, help="Path to runs JSONL file")
    parser.add_argument("--baseline-sec", dest="baseline_sec", type=float, default=3600.0)
    parser.add_argument("--recent-sec", dest="recent_sec", type=float, default=600.0)
    parser.add_argument("--binding", dest="binding", type=str, default=None, help="Filter by binding id")
    parser.add_argument("--arm", dest="arm", type=str, default=None, help="Filter by selected arm")
    parser.add_argument(
        "--weights-config",
        dest="weights_config",
        type=Path,
        default=None,
        help="Optional trace-mind.toml path for reward weights",
    )
    parser.add_argument(
        "--output",
        dest="output",
        type=Path,
        default=Path("reports/offline_eval.json"),
        help="Where to write JSON report",
    )
    return parser.parse_args(argv)


def _load_runs(path: Path) -> List[Dict[str, object]]:
    runs: List[Dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            runs.append(json.loads(stripped))
    return runs


def _coerce_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_task_success(meta: Dict[str, object]) -> Optional[float]:
    ts = meta.get("task_success")
    if ts is None:
        return None
    try:
        return float(ts)
    except (TypeError, ValueError):
        return None


def _normalize_run(raw: Dict[str, object], *, weights) -> Optional[_Run]:
    binding = raw.get("binding") or raw.get("policy_binding") or raw.get("flow")
    arm = raw.get("selected_flow") or raw.get("arm") or raw.get("flow")
    status = (raw.get("status") or "").lower() or "error"
    outcome = (raw.get("outcome") or status or "error").lower()
    try:
        end_ts = float(raw.get("end_ts"))
    except (TypeError, ValueError):
        return None

    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    duration_ms = _coerce_float(raw.get("duration_ms"))
    cost_usd = _coerce_float(raw.get("cost_usd"))
    user_rating = raw.get("user_rating")
    if user_rating is not None:
        try:
            user_rating = float(user_rating)
        except (TypeError, ValueError):
            user_rating = None

    reward_value = raw.get("reward")
    if reward_value is None:
        event = FeedbackEvent(
            outcome=outcome if outcome in {"ok", "error", "rejected"} else "error",
            duration_ms=duration_ms,
            cost_usd=cost_usd or None,
            user_rating=user_rating,
            task_success=_extract_task_success(meta),
            extras=dict(meta),
        )
        reward_value = reward(event, weights)
    else:
        reward_value = _coerce_float(reward_value)

    if not isinstance(binding, str) or not isinstance(arm, str):
        return None

    return _Run(
        binding=binding,
        arm=arm,
        status=status,
        outcome=outcome,
        duration_ms=duration_ms,
        cost_usd=cost_usd,
        user_rating=user_rating if isinstance(user_rating, float) else None,
        end_ts=end_ts,
        reward_value=float(reward_value),
        meta=dict(meta),
    )


def _group_metrics(runs: Iterable[_Run], window_sec: float, latest_ts: float) -> Dict[Tuple[str, str], _Metrics]:
    metrics: Dict[Tuple[str, str], _Metrics] = {}
    if window_sec <= 0:
        return metrics
    cutoff = latest_ts - window_sec
    for run in runs:
        if run.end_ts < cutoff:
            continue
        key = (run.binding, run.arm)
        metrics.setdefault(key, _Metrics()).add(run)
    return metrics


def _compute_deltas(
    baseline: Dict[Tuple[str, str], _Metrics],
    recent: Dict[Tuple[str, str], _Metrics],
) -> Dict[Tuple[str, str], Dict[str, float]]:
    keys = set(baseline) | set(recent)
    deltas: Dict[Tuple[str, str], Dict[str, float]] = {}
    for key in keys:
        b = baseline.get(key, _Metrics())
        r = recent.get(key, _Metrics())
        b_dict = b.as_dict()
        r_dict = r.as_dict()
        deltas[key] = {
            "ok_rate": r_dict["ok_rate"] - b_dict["ok_rate"],
            "avg_reward": r_dict["avg_reward"] - b_dict["avg_reward"],
            "avg_latency_ms": r_dict["avg_latency_ms"] - b_dict["avg_latency_ms"],
            "avg_cost_usd": r_dict["avg_cost_usd"] - b_dict["avg_cost_usd"],
            "n": r_dict["n"] - b_dict["n"],
        }
    return deltas


def _format_table(
    recent: Dict[Tuple[str, str], _Metrics],
    baseline: Dict[Tuple[str, str], _Metrics],
    deltas: Dict[Tuple[str, str], Dict[str, float]],
) -> str:
    headers = (
        f"{'Binding':<24} {'Arm':<20} {'n':>6} {'ok_rate':>8} {'latency_ms':>12} "
        f"{'cost_usd':>10} {'reward':>9} {'Δreward':>9}"
    )
    lines = [headers, "-" * len(headers)]
    for binding, arm in sorted(recent.keys() | baseline.keys(), key=lambda item: (item[0], item[1])):
        rec = recent.get((binding, arm), _Metrics()).as_dict()
        delta = deltas.get((binding, arm), {})
        lines.append(
            f"{binding:<24} {arm:<20} {rec['n']:6d} {rec['ok_rate']:8.2%} {rec['avg_latency_ms']:12.1f} "
            f"{rec['avg_cost_usd']:10.4f} {rec['avg_reward']:9.3f} {delta.get('avg_reward', 0.0):9.3f}"
        )
    return "\n".join(lines)


def _write_json(
    output_path: Path,
    *,
    baseline: Dict[Tuple[str, str], _Metrics],
    recent: Dict[Tuple[str, str], _Metrics],
    deltas: Dict[Tuple[str, str], Dict[str, float]],
    params: Dict[str, object],
) -> None:
    structured: Dict[str, Dict[str, Dict[str, Dict[str, float]]]] = {}
    for key in baseline.keys() | recent.keys() | deltas.keys():
        binding, arm = key
        binding_bucket = structured.setdefault(binding, {})
        arm_bucket = binding_bucket.setdefault(arm, {})
        arm_bucket["baseline"] = baseline.get(key, _Metrics()).as_dict()
        arm_bucket["recent"] = recent.get(key, _Metrics()).as_dict()
        arm_bucket["delta"] = deltas.get(
            key, {"ok_rate": 0.0, "avg_reward": 0.0, "avg_latency_ms": 0.0, "avg_cost_usd": 0.0, "n": 0.0}
        )
    payload = {"params": params, "bindings": structured}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = _parse_args(argv)
    raw_runs = _load_runs(args.from_jsonl)
    weights_path = args.weights_config
    default_weights = load_reward_weights(weights_path)

    normalized: List[_Run] = []
    for raw in raw_runs:
        run = _normalize_run(raw, weights=default_weights)
        if run is None:
            continue
        if args.binding and run.binding != args.binding:
            continue
        if args.arm and run.arm != args.arm:
            continue
        normalized.append(run)

    if not normalized:
        print("No runs matched filters", file=sys.stderr)
        return 1

    latest_ts = max(run.end_ts for run in normalized)

    baseline_metrics = _group_metrics(normalized, args.baseline_sec, latest_ts)
    recent_metrics = _group_metrics(normalized, args.recent_sec, latest_ts)
    deltas = _compute_deltas(baseline_metrics, recent_metrics)

    table = _format_table(recent_metrics, baseline_metrics, deltas)
    print(table)

    params = {
        "baseline_sec": args.baseline_sec,
        "recent_sec": args.recent_sec,
        "binding_filter": args.binding,
        "arm_filter": args.arm,
        "source": str(args.from_jsonl),
    }
    _write_json(args.output, baseline=baseline_metrics, recent=recent_metrics, deltas=deltas, params=params)
    print(f"\nReport written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
