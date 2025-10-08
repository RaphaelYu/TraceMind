from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple, Optional
from .engine import Plan, StepSpec, Rule

# -----------------------------
# Public data model
# -----------------------------


@dataclass
class Conflict:
    kind: str  # "write-write" | "suspicious-rule"
    where: str  # rule name or "cross-rule"
    a: str  # step A name (or trigger expr)
    b: str  # step B name (optional/empty if N/A)
    detail: str


@dataclass
class Coverage:
    # What triggers and steps are used / unused, and whether user-provided focus fields are covered
    unused_steps: List[str]
    unreachable_steps: List[str]  # alias of unused in many cases (kept for clarity)
    empty_rules: List[str]  # rules with no steps
    empty_triggers: List[str]  # rules with no triggers
    focus_uncovered: List[str]  # user-provided fields not matched by any rule.trigger


@dataclass
class Graphs:
    # Dependency graph between steps (writes -> reads)
    step_deps: Dict[str, List[str]]  # edges A->B means A writes something B reads
    topo: List[str]  # if cycle-free; otherwise empty
    cycles: List[List[str]]  # list of cycles if any


@dataclass
class AnalysisReport:
    graphs: Graphs
    conflicts: List[Conflict]
    coverage: Coverage
    dot_rules_steps: str  # DOT: rules -> steps sequence
    dot_step_deps: str  # DOT: step dependency graph


# -----------------------------
# Helpers
# -----------------------------


def _first_segment(expr: str) -> str:
    # "services[].name" -> "services[]"
    # "a.b[0].c" -> "a"
    s = expr.split(".", 1)[0]
    # normalize "[N]" to "[]"
    if "[" in s and "]" in s:
        left = s[: s.index("[")]
        return left + "[]"
    return s


def _writes_overlap(a: str, b: str) -> bool:
    """
    Conservative prefix overlap test between two write selectors.
    If first segment equal, consider potentially overlapping.
    """
    return _first_segment(a) == _first_segment(b)


def _write_affects_read(write_sel: str, read_sel: str) -> bool:
    """
    Conservative: if first segments match, assume write could affect read.
    This keeps analysis simple and safe; you can swap in a precise matcher later.
    """
    return _first_segment(write_sel) == _first_segment(read_sel)


def _topological_order(graph: Dict[str, List[str]]) -> Tuple[List[str], List[List[str]]]:
    indeg = {k: 0 for k in graph}
    for u, vs in graph.items():
        for v in vs:
            indeg[v] = indeg.get(v, 0) + 1
    q = [n for n, d in indeg.items() if d == 0]
    order: List[str] = []
    while q:
        cur = q.pop(0)
        order.append(cur)
        for v in graph.get(cur, []):
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    if len(order) != len(graph):
        # find cycles (simple DFS)
        cycles = _find_cycles(graph)
        return [], cycles
    return order, []


def _find_cycles(graph: Dict[str, List[str]]) -> List[List[str]]:
    seen, stack, cycles = set(), [], []

    def dfs(u: str):
        seen.add(u)
        stack.append(u)
        for v in graph.get(u, []):
            if v not in seen:
                dfs(v)
            elif v in stack:
                i = stack.index(v)
                cycles.append(stack[i:] + [v])
        stack.pop()

    for n in graph:
        if n not in seen:
            dfs(n)
    return cycles


# -----------------------------
# Main analysis
# -----------------------------


def analyze_plan(plan: Plan, focus_fields: Optional[List[str]] = None) -> AnalysisReport:
    steps: Dict[str, StepSpec] = plan.steps
    rules: List[Rule] = plan.rules

    # 1) Step dependency graph by writes->reads
    dep: Dict[str, List[str]] = {k: [] for k in steps.keys()}
    for a in steps.values():
        for b in steps.values():
            if a.name == b.name:
                continue
            if any(_write_affects_read(w, r) for w in a.writes for r in b.reads):
                dep[a.name].append(b.name)

    topo, cycles = _topological_order(dep)

    graphs = Graphs(step_deps=dep, topo=topo, cycles=cycles)

    # 2) Conflicts
    conflicts: List[Conflict] = []
    # 2a) write-write conflicts within the same rule sequence
    for r in rules:
        for i in range(len(r.steps)):
            si = steps[r.steps[i]]
            for j in range(i + 1, len(r.steps)):
                sj = steps[r.steps[j]]
                if any(_writes_overlap(w1, w2) for w1 in si.writes for w2 in sj.writes):
                    conflicts.append(
                        Conflict(
                            kind="write-write",
                            where=r.name,
                            a=si.name,
                            b=sj.name,
                            detail=f"Potential overlapping writes in rule order: '{si.name}' -> '{sj.name}'",
                        )
                    )
    # 2b) cross-rule potential conflicts (very conservative)
    # if two steps write overlapping prefixes and their rules share any trigger first-segment
    rule_trig_heads: Dict[str, Set[str]] = {}
    for r in rules:
        heads = {_first_segment(t) for t in r.triggers}
        rule_trig_heads[r.name] = heads
    for i in range(len(rules)):
        ri = rules[i]
        for j in range(i + 1, len(rules)):
            rj = rules[j]
            if rule_trig_heads[ri.name].intersection(rule_trig_heads[rj.name]):
                # same trigger head -> may co-fire
                for si_name in ri.steps:
                    for sj_name in rj.steps:
                        si, sj = steps[si_name], steps[sj_name]
                        if any(_writes_overlap(w1, w2) for w1 in si.writes for w2 in sj.writes):
                            conflicts.append(
                                Conflict(
                                    kind="write-write",
                                    where="cross-rule",
                                    a=f"{ri.name}:{si.name}",
                                    b=f"{rj.name}:{sj.name}",
                                    detail="Rules may co-fire (shared trigger head) and write overlapping prefixes.",
                                )
                            )

    # suspicious rules: empty triggers or steps
    empty_rules = [r.name for r in rules if not r.steps]
    empty_triggers = [r.name for r in rules if not r.triggers]
    for rn in empty_rules:
        conflicts.append(Conflict(kind="suspicious-rule", where=rn, a="", b="", detail="Rule has no steps."))
    for rn in empty_triggers:
        conflicts.append(Conflict(kind="suspicious-rule", where=rn, a="", b="", detail="Rule has no triggers."))

    # 3) Coverage
    referenced_steps: Set[str] = set(s for r in rules for s in r.steps)
    all_steps: Set[str] = set(steps.keys())
    unused_steps = sorted(list(all_steps - referenced_steps))
    unreachable_steps = unused_steps[:]  # same meaning for now

    focus_uncovered: List[str] = []
    if focus_fields:
        trig_heads_all = {_first_segment(t) for r in rules for t in r.triggers}
        for f in focus_fields:
            if _first_segment(f) not in trig_heads_all:
                focus_uncovered.append(f)

    coverage = Coverage(
        unused_steps=unused_steps,
        unreachable_steps=unreachable_steps,
        empty_rules=empty_rules,
        empty_triggers=empty_triggers,
        focus_uncovered=focus_uncovered,
    )

    # 4) DOT exports
    dot_rules_steps = export_dot_rules_steps(plan)
    dot_step_deps = export_dot_step_deps(dep, cycles)

    return AnalysisReport(
        graphs=graphs,
        conflicts=conflicts,
        coverage=coverage,
        dot_rules_steps=dot_rules_steps,
        dot_step_deps=dot_step_deps,
    )


# -----------------------------
# DOT exporters
# -----------------------------


def export_dot_rules_steps(plan: Plan) -> str:
    lines = ["digraph G { rankdir=LR; node [shape=box,style=rounded];"]
    for r in plan.rules:
        lines.append(f'"R:{r.name}" [shape=box,style=rounded,color=blue]')
        prev = f"R:{r.name}"
        for s in r.steps:
            lines.append(f'"S:{s}" [shape=ellipse]')
            lines.append(f'"{prev}" -> "S:{s}"')
            prev = f"S:{s}"
    lines.append("}")
    return "\n".join(lines)


def export_dot_step_deps(step_graph: Dict[str, List[str]], cycles: List[List[str]] | None = None) -> str:
    cyc_nodes = set(n for cyc in (cycles or []) for n in cyc)
    lines = ["digraph G { rankdir=LR; node [shape=ellipse];"]
    for u, vs in step_graph.items():
        color = "red" if u in cyc_nodes else "black"
        lines.append(f'"{u}" [color={color}]')
        for v in vs:
            lines.append(f'"{u}" -> "{v}"')
    lines.append("}")
    return "\n".join(lines)
