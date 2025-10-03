# tm/cli.py
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping
from datetime import datetime, timedelta, timezone
from tm.app.demo_plan import build_plan
from tm.pipeline.analysis import analyze_plan
from tm.obs.retrospect import load_window
from tm.scaffold import create_flow, create_policy, init_project, find_project_root
from tm.run_recipe import run_recipe
from tm.governance.audit import AuditTrail
from tm.governance.config import load_governance_config
from tm.governance.hitl import HitlManager
from tm.runtime.workers import WorkerOptions, TaskWorkerSupervisor, install_signal_handlers
from tm.runtime.dlq import DeadLetterStore
from tm.runtime.queue import FileWorkQueue
from tm.runtime.idempotency import IdempotencyStore
from tm.runtime.queue.manager import TaskQueueManager
from tm.runtime.retry import load_retry_policy

def _cmd_pipeline_analyze(args):
    plan = build_plan()
    focus = args.focus or []
    rep = analyze_plan(plan, focus_fields=focus)

    # Print summary
    print("== Step dependency topo ==")
    if rep.graphs.topo:
        print(" -> ".join(rep.graphs.topo))
    else:
        print("CYCLES detected:")
        for cyc in rep.graphs.cycles:
            print("  - " + " -> ".join(cyc))

    print("\n== Conflicts ==")
    if not rep.conflicts:
        print("  (none)")
    else:
        for c in rep.conflicts:
            print(f"  [{c.kind}] where={c.where} a={c.a} b={c.b} detail={c.detail}")

    print("\n== Coverage ==")
    print("  unused_steps:", rep.coverage.unused_steps or "[]")
    print("  empty_rules:", rep.coverage.empty_rules or "[]")
    print("  empty_triggers:", rep.coverage.empty_triggers or "[]")
    if rep.coverage.focus_uncovered:
        print("  focus_uncovered:", rep.coverage.focus_uncovered)

def _cmd_pipeline_export_dot(args):
    plan = build_plan()
    rep = analyze_plan(plan)
    with open(args.out_rules_steps, "w", encoding="utf-8") as f:
        f.write(rep.dot_rules_steps)
    with open(args.out_step_deps, "w", encoding="utf-8") as f:
        f.write(rep.dot_step_deps)
    print("DOT files written:",
          args.out_rules_steps, "and", args.out_step_deps)


def _build_hitl_manager(config_path: str) -> HitlManager:
    cfg = load_governance_config(config_path)
    hitl_cfg = cfg.hitl
    if not hitl_cfg.enabled:
        raise RuntimeError("HITL approvals are disabled in configuration")
    return HitlManager(hitl_cfg, audit=AuditTrail(cfg.audit))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TraceMind CLI")
    sub = parser.add_subparsers(dest="cmd")

    sp = sub.add_parser("pipeline", help="pipeline tools")
    ssp = sp.add_subparsers(dest="pcmd")

    sp_an = ssp.add_parser("analyze", help="analyze current plan")
    sp_an.add_argument("--focus", nargs="*", help="fields to check coverage (e.g. services[].state status)")
    sp_an.set_defaults(func=_cmd_pipeline_analyze)

    sp_dot = ssp.add_parser("export-dot", help="export DOT graphs")
    sp_dot.add_argument("--out-rules-steps", required=True, help="output .dot for rule->steps")
    sp_dot.add_argument("--out-step-deps", required=True, help="output .dot for step dependency graph")
    sp_dot.set_defaults(func=_cmd_pipeline_export_dot)

    def _parse_duration(expr: str) -> timedelta:
        units = {"s": 1, "m": 60, "h": 3600}
        try:
            factor = units[expr[-1]]
            value = float(expr[:-1])
            return timedelta(seconds=value * factor)
        except Exception as exc:
            raise ValueError(f"Invalid duration '{expr}'") from exc

    def _cmd_metrics_dump(args):
        window = _parse_duration(args.window)
        until = datetime.now(timezone.utc)
        since = until - window
        entries = load_window(args.dir, since, until)
        if args.format == "csv":
            print("type,name,labels,value")
            for entry in entries:
                label_str = ";".join(f"{k}={v}" for k, v in sorted(entry["labels"].items()))
                print(f"{entry['type']},{entry['name']},{label_str},{entry['value']}")
        else:
            print(json.dumps(entries, indent=2))

    sp_metrics = sub.add_parser("metrics", help="metrics tools")
    spm_sub = sp_metrics.add_subparsers(dest="mcmd")
    spm_dump = spm_sub.add_parser("dump", help="dump metrics window")
    spm_dump.add_argument("--dir", required=True, help="binlog directory")
    spm_dump.add_argument("--window", default="5m", help="window size (e.g. 5m, 1h)")
    spm_dump.add_argument("--format", choices=["csv", "json"], default="csv")
    spm_dump.set_defaults(func=_cmd_metrics_dump)

    approve_parser = sub.add_parser("approve", help="manage human approvals")
    approve_parser.add_argument("--config", default="trace-mind.toml", help="governance config path")
    approve_parser.add_argument("--list", action="store_true", help="list pending approvals")
    approve_parser.add_argument("approval_id", nargs="?", help="approval identifier")
    approve_parser.add_argument("--decision", choices=["approve", "deny"], help="decision to apply")
    approve_parser.add_argument("--actor", default="cli", help="actor identifier")
    approve_parser.add_argument("--note", help="optional note")

    def _cmd_approve(args):
        try:
            manager = _build_hitl_manager(args.config)
        except Exception as exc:  # pragma: no cover - CLI error path
            print(str(exc), file=sys.stderr)
            sys.exit(1)

        if args.list:
            records = manager.pending()
            if not records:
                print("(no pending approvals)")
                return
            for record in records:
                print(json.dumps(
                    {
                        "approval_id": record.approval_id,
                        "flow": record.flow,
                        "step": record.step,
                        "reason": record.reason,
                        "actors": list(record.actors),
                        "created_at": record.created_at,
                        "ttl_ms": record.ttl_ms,
                    },
                    ensure_ascii=False,
                ))
            return

        if not args.approval_id or not args.decision:
            print("approval_id and --decision are required unless using --list", file=sys.stderr)
            sys.exit(1)

        try:
            record = manager.decide(
                args.approval_id,
                decision=args.decision,
                actor=args.actor or "cli",
                note=args.note,
            )
        except Exception as exc:  # pragma: no cover - CLI error path
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        else:
            print(json.dumps(
                {
                    "approval_id": record.approval_id,
                    "decision": record.status,
                    "actor": record.decided_by,
                    "note": record.note,
                },
                ensure_ascii=False,
            ))

    approve_parser.set_defaults(func=_cmd_approve)

    init_parser = sub.add_parser("init", help="initialize a new TraceMind project")
    init_parser.add_argument("project_name", help="project directory to create")
    init_parser.add_argument("--with-prom", action="store_true", help="include Prometheus hook scaffold")
    init_parser.add_argument("--with-retrospect", action="store_true", help="include Retrospect exporter scaffold")
    init_parser.add_argument("--force", action="store_true", help="overwrite existing scaffold files")

    def _cmd_init(args):
        try:
            init_project(
                args.project_name,
                Path.cwd(),
                with_prom=args.with_prom,
                with_retrospect=args.with_retrospect,
                force=args.force,
            )
        except FileExistsError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Project '{args.project_name}' ready")

    init_parser.set_defaults(func=_cmd_init)

    new_parser = sub.add_parser("new", help="generate project assets")
    new_sub = new_parser.add_subparsers(dest="asset")

    flow_parser = new_sub.add_parser("flow", help="create a flow skeleton")
    flow_parser.add_argument("flow_name", help="flow name")
    variant = flow_parser.add_mutually_exclusive_group()
    variant.add_argument("--switch", action="store_true", help="include a switch step")
    variant.add_argument("--parallel", action="store_true", help="include a parallel step")

    def _cmd_new_flow(args):
        try:
            root = find_project_root(Path.cwd())
            created = create_flow(args.flow_name, project_root=root, switch=args.switch, parallel=args.parallel)
        except Exception as exc:  # pragma: no cover - CLI error path
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Flow created: {created.relative_to(root)}")

    flow_parser.set_defaults(func=_cmd_new_flow)

    policy_parser = new_sub.add_parser("policy", help="create a policy skeleton")
    policy_parser.add_argument("policy_name", help="policy identifier")
    strategy = policy_parser.add_mutually_exclusive_group()
    strategy.add_argument("--epsilon", action="store_true", help="generate epsilon-greedy policy")
    strategy.add_argument("--ucb", action="store_true", help="generate UCB policy")
    policy_parser.add_argument("--mcp-endpoint", help="default MCP endpoint", default=None)

    def _cmd_new_policy(args):
        try:
            root = find_project_root(Path.cwd())
            strat = "ucb" if args.ucb else "epsilon"
            created = create_policy(args.policy_name, project_root=root, strategy=strat, mcp_endpoint=args.mcp_endpoint)
        except Exception as exc:  # pragma: no cover - CLI error path
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Policy created: {created.relative_to(root)}")

    policy_parser.set_defaults(func=_cmd_new_policy)

    run_parser = sub.add_parser("run", help="execute a flow recipe")
    run_parser.add_argument("recipe", help="path to recipe (JSON or YAML)")
    run_parser.add_argument("-i", "--input", help="JSON string or @file with initial state")

    def _cmd_run(args):
        payload: Dict[str, Any]
        if args.input:
            raw = args.input
            if raw.startswith("@"):
                data = Path(raw[1:]).read_text(encoding="utf-8")
            else:
                data = raw
            try:
                payload_obj = json.loads(data)
            except json.JSONDecodeError as exc:  # pragma: no cover - CLI error path
                print(f"Invalid input JSON: {exc}", file=sys.stderr)
                sys.exit(1)
            if not isinstance(payload_obj, dict):
                print("Input JSON must decode to an object", file=sys.stderr)
                sys.exit(1)
            payload = payload_obj
        else:
            payload = {}

        result = run_recipe(Path(args.recipe), payload)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    run_parser.set_defaults(func=_cmd_run)

    workers_parser = sub.add_parser("workers", help="manage worker processes")
    workers_sub = workers_parser.add_subparsers(dest="wcmd")

    workers_start = workers_sub.add_parser("start", help="start worker pool")
    workers_start.add_argument("-n", "--num", dest="worker_count", type=int, default=1, help="number of worker processes")
    workers_start.add_argument("--queue", choices=["file", "memory"], default="file", help="queue backend")
    workers_start.add_argument("--queue-dir", default="data/queue", help="queue directory (file backend)")
    workers_start.add_argument("--idempotency-dir", default="data/idempotency", help="idempotency cache directory")
    workers_start.add_argument("--dlq-dir", default="data/dlq", help="dead letter queue directory")
    workers_start.add_argument(
        "--runtime",
        default="tm.app.wiring_flows:_runtime",
        help="runtime factory in module:attr format",
    )
    workers_start.add_argument("--lease-ms", type=int, default=30_000, help="lease duration in milliseconds")
    workers_start.add_argument("--batch", type=int, default=1, help="tasks to lease per fetch")
    workers_start.add_argument("--poll", type=float, default=0.5, help="poll interval when idle (seconds)")
    workers_start.add_argument("--heartbeat", type=float, default=5.0, help="heartbeat interval (seconds)")
    workers_start.add_argument("--heartbeat-timeout", type=float, default=15.0, help="heartbeat timeout before restart (seconds)")
    workers_start.add_argument("--result-ttl", type=float, default=3600.0, help="idempotency result TTL (seconds)")
    workers_start.add_argument("--config", help="config file for retry policies", default="trace_config.toml")
    workers_start.add_argument("--drain-grace", type=float, default=10.0, help="grace period (s) when draining")

    def _cmd_workers_start(args):
        opts = WorkerOptions(
            worker_count=args.worker_count,
            queue_backend=args.queue,
            queue_dir=str(Path(args.queue_dir).resolve()),
            idempotency_dir=str(Path(args.idempotency_dir).resolve()),
            dlq_dir=str(Path(args.dlq_dir).resolve()),
            runtime_spec=args.runtime,
            lease_ms=args.lease_ms,
            batch_size=args.batch,
            poll_interval=args.poll,
            heartbeat_interval=args.heartbeat,
            heartbeat_timeout=args.heartbeat_timeout,
            result_ttl=args.result_ttl,
            config_path=str(Path(args.config).resolve()) if args.config else None,
            drain_grace=args.drain_grace,
        )
        supervisor = TaskWorkerSupervisor(opts)
        install_signal_handlers(supervisor)
        supervisor.run_forever()

    workers_start.set_defaults(func=_cmd_workers_start)

    dlq_parser = sub.add_parser("dlq", help="dead letter queue tools")
    dlq_sub = dlq_parser.add_subparsers(dest="dlqcmd")

    dlq_ls = dlq_sub.add_parser("ls", help="list DLQ entries")
    dlq_ls.add_argument("--dlq-dir", default="data/dlq", help="dead letter directory")
    dlq_ls.add_argument("--limit", type=int, default=20, help="maximum entries to display")

    def _cmd_dlq_ls(args):
        store = DeadLetterStore(args.dlq_dir)
        count = 0
        for record in store.list():
            print(
                json.dumps(
                    {
                        "entry_id": record.entry_id,
                        "flow_id": record.flow_id,
                        "attempt": record.attempt,
                        "timestamp": record.timestamp,
                        "error": record.error,
                    },
                    ensure_ascii=False,
                )
            )
            count += 1
            if args.limit and count >= args.limit:
                break

    dlq_ls.set_defaults(func=_cmd_dlq_ls)

    dlq_requeue = dlq_sub.add_parser("requeue", help="requeue a DLQ entry")
    dlq_requeue.add_argument("entry_id", help="DLQ entry identifier")
    dlq_requeue.add_argument("--dlq-dir", default="data/dlq")
    dlq_requeue.add_argument("--queue-dir", default="data/queue")
    dlq_requeue.add_argument("--idempotency-dir", default="data/idempotency")
    dlq_requeue.add_argument("--config", default="trace_config.toml")

    def _cmd_dlq_requeue(args):
        store = DeadLetterStore(args.dlq_dir)
        record = store.load(args.entry_id)
        if record is None:
            print(f"entry '{args.entry_id}' not found", file=sys.stderr)
            sys.exit(1)
        queue = FileWorkQueue(str(Path(args.queue_dir).resolve()))
        idem = IdempotencyStore(dir_path=str(Path(args.idempotency_dir).resolve()))
        policy = load_retry_policy(args.config)
        manager = TaskQueueManager(queue, idem, retry_policy=policy)
        headers = dict(record.task.get("headers", {})) if isinstance(record.task, Mapping) else {}
        trace = record.task.get("trace") if isinstance(record.task, Mapping) else {}
        outcome = manager.enqueue(
            flow_id=record.flow_id,
            input=record.task.get("input", {}),
            headers=headers,
            trace=trace if isinstance(trace, Mapping) else {},
        )
        queue.flush()
        queue.close()
        store.consume(record.entry_id, state="requeued")
        if outcome.envelope:
            print(f"requeued {record.entry_id} -> task {outcome.envelope.task_id}")

    dlq_requeue.set_defaults(func=_cmd_dlq_requeue)

    dlq_purge = dlq_sub.add_parser("purge", help="purge a DLQ entry")
    dlq_purge.add_argument("entry_id", help="DLQ entry identifier")
    dlq_purge.add_argument("--dlq-dir", default="data/dlq")

    def _cmd_dlq_purge(args):
        store = DeadLetterStore(args.dlq_dir)
        record = store.consume(args.entry_id, state="purged")
        if record is None:
            print(f"entry '{args.entry_id}' not found", file=sys.stderr)
            sys.exit(1)
        print(f"purged {args.entry_id}")

    dlq_purge.set_defaults(func=_cmd_dlq_purge)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        # fallback: keep old behavior (imported by Hypercorn)
        pass
