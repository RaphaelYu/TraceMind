from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence


@dataclass
class LockRequest:
    name: str
    mode: str  # "shared" or "exclusive"


@dataclass
class StepSpec:
    id: str
    next_steps: Sequence[str]
    locks: Sequence[LockRequest]
    duration_ms: int


@dataclass
class FlowSpec:
    id: str
    steps: Dict[str, StepSpec]
    entrypoints: Sequence[str]


@dataclass
class StepState:
    spec: StepSpec
    acquired_index: int = 0
    held_locks: List[LockRequest] = field(default_factory=list)
    started_at: Optional[int] = None
    finished_at: Optional[int] = None


@dataclass
class SimulationReport:
    finished: int
    deadlocks: int
    events: List[Dict[str, object]]


def _parse_lock_requests(raw: Iterable[Mapping[str, object]] | None) -> Sequence[LockRequest]:
    if not raw:
        return ()
    locks: list[LockRequest] = []
    for entry in raw:
        mode = str(entry.get("mode", "exclusive")).lower()
        if mode not in {"exclusive", "shared"}:
            mode = "exclusive"
        locks.append(LockRequest(name=str(entry.get("name")), mode=mode))
    return tuple(locks)


def _parse_flow(flow_doc: Mapping[str, object]) -> FlowSpec:
    flow_id = str(flow_doc.get("id", "flow"))
    steps_doc = flow_doc.get("steps")
    if not isinstance(steps_doc, Mapping):
        raise ValueError("flow missing steps mapping")
    steps: Dict[str, StepSpec] = {}
    incoming: Dict[str, int] = {}
    for raw_id, raw_spec in steps_doc.items():
        node_id = str(raw_id)
        spec = raw_spec or {}
        if not isinstance(spec, Mapping):
            raise ValueError(f"step '{node_id}' must be mapping")
        next_field = spec.get("next", [])
        if isinstance(next_field, str):
            next_list = [next_field]
        elif isinstance(next_field, Iterable):
            next_list = [str(item) for item in next_field]
        else:
            next_list = []
        next_steps = tuple(next_list)
        locks = _parse_lock_requests(spec.get("locks"))
        duration = spec.get("duration_ms", 50)
        try:
            duration_ms = max(1, int(duration))
        except Exception:
            duration_ms = 50
        steps[node_id] = StepSpec(
            id=node_id,
            next_steps=next_steps,
            locks=locks,
            duration_ms=duration_ms,
        )
        for target in next_steps:
            incoming[target] = incoming.get(target, 0) + 1

    entry_candidates = sorted(step for step in steps if incoming.get(step, 0) == 0)
    if not entry_candidates and steps:
        entry_candidates = [sorted(steps.keys())[0]]
    entry = tuple(entry_candidates)

    return FlowSpec(id=flow_id, steps=steps, entrypoints=entry)


def simulate(
    flow_doc: Mapping[str, object], *, at: str | None = None, seed: int | None = None, max_concurrency: int = 1
) -> Dict[str, object]:
    flow = _parse_flow(flow_doc)
    rng = random.Random(seed if seed is not None else 0)
    now = 0
    events: list[Dict[str, object]] = []
    running: list[StepState] = []
    completed: Dict[str, StepState] = {}
    scheduled: Dict[str, StepState] = {}
    waiting: list[StepState] = []
    locks_held: Dict[str, Dict[str, int]] = {}

    def can_acquire(req: LockRequest) -> bool:
        slot = locks_held.get(req.name)
        if not slot:
            return True
        if req.mode == "exclusive":
            return slot.get("shared", 0) == 0 and slot.get("exclusive", 0) == 0
        return slot.get("exclusive", 0) == 0

    def acquire(req: LockRequest) -> None:
        slot = locks_held.setdefault(req.name, {"shared": 0, "exclusive": 0})
        slot[req.mode] += 1

    def release(requests: Sequence[LockRequest]) -> None:
        for req in requests:
            slot = locks_held.get(req.name)
            if not slot:
                continue
            slot[req.mode] = max(0, slot.get(req.mode, 0) - 1)
            if slot["shared"] == 0 and slot["exclusive"] == 0:
                locks_held.pop(req.name, None)

    for step_id in flow.entrypoints:
        spec = flow.steps.get(step_id)
        if not spec:
            continue
        state = StepState(spec=spec)
        scheduled[spec.id] = state
        waiting.append(state)

    while waiting or running:
        progress = False

        candidates = waiting.copy()
        rng.shuffle(candidates)
        for state in candidates:
            if state.acquired_index < len(state.spec.locks):
                req = state.spec.locks[state.acquired_index]
                if can_acquire(req):
                    acquire(req)
                    state.held_locks.append(req)
                    state.acquired_index += 1
                    progress = True
            if (
                state.acquired_index == len(state.spec.locks)
                and state in waiting
                and len(running) < max(1, max_concurrency)
            ):
                waiting.remove(state)
                state.started_at = now
                running.append(state)
                events.append({"event": "step_started", "step": state.spec.id, "ts": now})
                progress = True

        if running:
            running.sort(key=lambda s: s.started_at or now)
            current = running.pop(0)
            finish_time = (current.started_at or now) + current.spec.duration_ms
            now = max(now, finish_time)
            current.finished_at = now
            release(current.held_locks)
            events.append({"event": "step_finished", "step": current.spec.id, "ts": now})
            completed[current.spec.id] = current
            progress = True

            for next_id in current.spec.next_steps:
                if next_id in completed or next_id in scheduled:
                    continue
                next_spec = flow.steps.get(next_id)
                if not next_spec:
                    continue
                next_state = StepState(spec=next_spec)
                scheduled[next_spec.id] = next_state
                waiting.append(next_state)

        if not progress:
            return {
                "finished": len(completed),
                "deadlocks": 1,
                "events": events,
                "locks_held": locks_held,
            }

    return {
        "finished": len(completed),
        "deadlocks": 0,
        "events": events,
    }
