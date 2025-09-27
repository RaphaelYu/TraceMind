# tm/cli.py
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone
from tm.app.demo_plan import build_plan
from tm.pipeline.analysis import analyze_plan
from tm.obs.retrospect import load_window
from tm.scaffold import create_flow, create_policy, init_project, find_project_root

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
            import json

            print(json.dumps(entries, indent=2))

    sp_metrics = sub.add_parser("metrics", help="metrics tools")
    spm_sub = sp_metrics.add_subparsers(dest="mcmd")
    spm_dump = spm_sub.add_parser("dump", help="dump metrics window")
    spm_dump.add_argument("--dir", required=True, help="binlog directory")
    spm_dump.add_argument("--window", default="5m", help="window size (e.g. 5m, 1h)")
    spm_dump.add_argument("--format", choices=["csv", "json"], default="csv")
    spm_dump.set_defaults(func=_cmd_metrics_dump)

    init_parser = sub.add_parser("init", help="initialize a new TraceMind project")
    init_parser.add_argument("project_name", help="project directory to create")
    init_parser.add_argument("--with-prom", action="store_true", help="include Prometheus hook scaffold")
    init_parser.add_argument("--with-retrospect", action="store_true", help="include Retrospect exporter scaffold")

    def _cmd_init(args):
        init_project(args.project_name, Path.cwd(), with_prom=args.with_prom, with_retrospect=args.with_retrospect)
        print(f"Project '{args.project_name}' created")

    init_parser.set_defaults(func=_cmd_init)

    new_parser = sub.add_parser("new", help="generate project assets")
    new_sub = new_parser.add_subparsers(dest="asset")

    flow_parser = new_sub.add_parser("flow", help="create a flow skeleton")
    flow_parser.add_argument("flow_name", help="flow name")
    variant = flow_parser.add_mutually_exclusive_group()
    variant.add_argument("--switch", action="store_true", help="include a switch step")
    variant.add_argument("--parallel", action="store_true", help="include a parallel step")

    def _cmd_new_flow(args):
        root = find_project_root(Path.cwd())
        create_flow(args.flow_name, project_root=root, switch=args.switch, parallel=args.parallel)
        print(f"Flow '{args.flow_name}' created")

    flow_parser.set_defaults(func=_cmd_new_flow)

    policy_parser = new_sub.add_parser("policy", help="create a policy skeleton")
    policy_parser.add_argument("policy_name", help="policy identifier")
    strategy = policy_parser.add_mutually_exclusive_group()
    strategy.add_argument("--epsilon", action="store_true", help="generate epsilon-greedy policy")
    strategy.add_argument("--ucb", action="store_true", help="generate UCB policy")
    policy_parser.add_argument("--mcp-endpoint", help="default MCP endpoint", default=None)

    def _cmd_new_policy(args):
        root = find_project_root(Path.cwd())
        strat = "ucb" if args.ucb else "epsilon"
        create_policy(args.policy_name, project_root=root, strategy=strat, mcp_endpoint=args.mcp_endpoint)
        print(f"Policy '{args.policy_name}' created")

    policy_parser.set_defaults(func=_cmd_new_policy)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        # fallback: keep old behavior (imported by Hypercorn)
        pass
