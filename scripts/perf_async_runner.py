#!/usr/bin/env python3
"""Async performance harness for FlowRuntime."""

from __future__ import annotations

import argparse
import asyncio
import time

from typing import Any, Dict

from tm.flow.operations import Operation
from tm.flow.runtime import FlowRuntime
from tm.flow.spec import FlowSpec, StepDef


class DummyFlow:
    def __init__(self, spec: FlowSpec) -> None:
        self._spec = spec

    @property
    def name(self) -> str:
        return self._spec.name

    def spec(self) -> FlowSpec:
        return self._spec


async def main() -> None:
    parser = argparse.ArgumentParser(description="FlowRuntime async benchmark")
    parser.add_argument("--requests", type=int, default=5000, help="total requests to issue")
    parser.add_argument("--concurrency", type=int, default=1000, help="number of concurrent tasks")
    parser.add_argument("--queue-capacity", type=int, default=2000, help="queue capacity")
    parser.add_argument("--run-delay-ms", type=float, default=0.0, help="per-request artificial delay")
    parser.add_argument("--idempotency", action="store_true", help="enable idempotency key reuse for all requests")
    args = parser.parse_args()

    delay = max(0.0, args.run_delay_ms / 1000.0)

    async def run_step(ctx, state):
        if delay:
            await asyncio.sleep(delay)
        return state

    spec = FlowSpec(name="perf")
    spec.add_step(
        StepDef(
            name="start",
            operation=Operation.TASK,
            next_steps=(),
            run=run_step,
        )
    )

    runtime = FlowRuntime(
        {spec.name: DummyFlow(spec)},
        max_concurrency=args.concurrency,
        queue_capacity=args.queue_capacity,
        queue_wait_timeout_ms=0,
        idempotency_ttl_sec=2.0,
        idempotency_cache_size=128,
    )

    async def worker(idx: int) -> Dict[str, Any]:  # type: ignore[name-defined]
        ctx = {"idempotency_key": "bench"} if args.idempotency else {}
        return await runtime.run("perf", inputs={"value": idx}, ctx=ctx)

    start = time.perf_counter()
    semaphore = asyncio.Semaphore(args.concurrency)

    async def sem_worker(i: int):
        async with semaphore:
            return await worker(i)

    tasks = [asyncio.create_task(sem_worker(i)) for i in range(args.requests)]
    await asyncio.gather(*tasks)
    end = time.perf_counter()

    await runtime.aclose()

    results = [t.result() for t in tasks]
    successes = sum(1 for r in results if r["status"] == "ok")
    rejected = sum(1 for r in results if r["status"] == "rejected")
    errors = sum(1 for r in results if r["status"] == "error")

    duration = end - start
    qps = args.requests / duration if duration > 0 else 0.0

    stats = runtime.get_stats()

    print("===== FlowRuntime Perf Summary =====")
    print(f"requests        : {args.requests}")
    print(f"concurrency     : {args.concurrency}")
    print(f"queue_capacity  : {args.queue_capacity}")
    print(f"run_delay_ms    : {args.run_delay_ms}")
    print(f"idempotency     : {args.idempotency}")
    print(f"duration_sec    : {duration:.3f}")
    print(f"throughput_qps  : {qps:.2f}")
    print(f"success         : {successes}")
    print(f"rejected        : {rejected}")
    print(f"errors          : {errors}")
    print("--- Latency ---")
    print(
        f"queue_ms p50/p95/p99 : {stats['queued_ms_p50']:.2f} / {stats['queued_ms_p95']:.2f} / {stats['queued_ms_p99']:.2f}"
    )
    print(
        f"exec_ms  p50/p95/p99 : {stats['exec_ms_p50']:.2f} / {stats['exec_ms_p95']:.2f} / {stats['exec_ms_p99']:.2f}"
    )
    print("--- Queue ---")
    print(f"queue_depth peak/current : {stats['queue_depth_peak']} / {stats['queue_depth_current']}")
    print(f"rejected_reason          : {stats['rejected_reason']}")
    print(f"success/error counts     : {stats['success']} / {stats['error']}")


if __name__ == "__main__":
    asyncio.run(main())
