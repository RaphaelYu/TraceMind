from __future__ import annotations

import json
import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

try:
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore

from .operations import Operation
from .spec import FlowSpec, StepDef


class RecipeError(ValueError):
    """Raised when a recipe cannot be parsed or validated."""


@dataclass
class RecipeLoader:
    """Load Flow recipes (JSON or YAML) and emit FlowSpec objects."""

    def load(self, source: str | Path) -> FlowSpec:
        data = self._read_source(source)
        recipe = self._extract_flow(data)
        return self._build_spec(recipe)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------
    def _read_source(self, source: str | Path) -> Dict[str, Any]:
        if isinstance(source, Path):
            path = source
            text = path.read_text(encoding="utf-8")
            hint = path.suffix.lower()
            return self._parse_text(text, hint)

        if isinstance(source, str):
            stripped = source.strip()
            if "\n" in source or stripped.startswith("{") or stripped.startswith("[") or stripped.startswith("flow:"):
                return self._parse_text(source, None)
            try:
                path = Path(source)
            except OSError:
                return self._parse_text(source, None)
            try:
                if path.exists():
                    text = path.read_text(encoding="utf-8")
                    hint = path.suffix.lower()
                    return self._parse_text(text, hint)
            except OSError:
                return self._parse_text(source, None)
            return self._parse_text(source, None)

        raise RecipeError("Unsupported recipe source type")

    def _parse_text(self, text: str, hint: Optional[str]) -> Dict[str, Any]:
        parsers: Iterable[str] = ()
        if hint in {".json"}:
            parsers = ("json", "yaml")
        elif hint in {".yml", ".yaml"}:
            parsers = ("yaml", "json")
        else:
            parsers = ("json", "yaml")

        last_exc: Optional[Exception] = None
        for kind in parsers:
            if kind == "json":
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as exc:
                    last_exc = exc
                else:
                    if isinstance(data, dict):
                        return data
                    last_exc = RecipeError("JSON recipe must decode to an object")
            elif kind == "yaml" and yaml is not None:
                try:
                    data = yaml.safe_load(text)
                except Exception as exc:  # pragma: no cover - PyYAML error path
                    last_exc = exc
                else:
                    if isinstance(data, dict):
                        return data
                    last_exc = RecipeError("YAML recipe must decode to an object")

        raise RecipeError(f"Failed to parse recipe: {last_exc}")

    # ------------------------------------------------------------------
    # FlowSpec construction
    # ------------------------------------------------------------------
    def _extract_flow(self, data: Dict[str, Any]) -> Dict[str, Any]:
        flow = data.get("flow")
        if not isinstance(flow, dict):
            raise RecipeError("Recipe missing 'flow' object")
        required = {"id", "version", "steps", "edges", "entry"}
        missing = required - flow.keys()
        if missing:
            raise RecipeError(f"Missing flow fields: {', '.join(sorted(missing))}")
        if not isinstance(flow["steps"], list) or not flow["steps"]:
            raise RecipeError("flow.steps must be a non-empty list")
        if not isinstance(flow["edges"], list):
            raise RecipeError("flow.edges must be a list")
        return flow

    def _build_spec(self, flow: Dict[str, Any]) -> FlowSpec:
        flow_id = self._expect_str(flow, "id")
        entry = self._expect_str(flow, "entry")

        spec = FlowSpec(name=flow_id, flow_id=flow_id)
        step_map: Dict[str, StepDef] = {}
        steps_data: list[Dict[str, Any]] = []
        for raw in flow["steps"]:
            if not isinstance(raw, dict):
                raise RecipeError("Each flow step must be an object")
            steps_data.append(raw)

        self._validate_unique_steps(steps_data)

        adjacency = self._build_adjacency(flow["edges"], steps_data)
        self._validate_graph(entry, steps_data, adjacency)

        for raw in steps_data:
            step = self._create_step(raw, adjacency)
            spec.add_step(step)
            step_map[step.name] = step

        spec.entrypoint = entry
        return spec

    # ------------------------------------------------------------------
    # Step helpers
    # ------------------------------------------------------------------
    def _create_step(self, raw: Dict[str, Any], adjacency: Dict[str, list[str]]) -> StepDef:
        step_id = self._expect_str(raw, "id")
        kind = self._expect_str(raw, "kind")
        try:
            op = Operation[kind.upper()]
        except KeyError as exc:
            raise RecipeError(f"Unsupported step kind '{kind}'") from exc

        config = raw.get("config") or {}
        if not isinstance(config, dict):
            raise RecipeError(f"Step '{step_id}' config must be an object")

        hooks = raw.get("hooks") or {}
        if hooks and not isinstance(hooks, dict):
            raise RecipeError(f"Step '{step_id}' hooks must be an object")

        before = self._resolve_hook(hooks.get("before"))
        run = self._resolve_hook(hooks.get("run"))
        after = self._resolve_hook(hooks.get("after"))
        on_error = self._resolve_hook(hooks.get("on_error"))

        if op is Operation.FINISH and run is not None:
            raise RecipeError(f"finish step '{step_id}' cannot define run hook")
        if op is not Operation.FINISH and run is None:
            raise RecipeError(f"Step '{step_id}' requires a run hook")

        timeout = raw.get("timeout_ms")
        if timeout is not None and (not isinstance(timeout, int) or timeout <= 0):
            raise RecipeError(f"Step '{step_id}' timeout_ms must be positive integer")

        self._validate_config(step_id, op, config, adjacency)

        next_steps = tuple(adjacency.get(step_id, ()))
        return StepDef(
            name=step_id,
            operation=op,
            next_steps=next_steps,
            config=config,
            before=before,
            run=run,
            after=after,
            on_error=on_error,
        )

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------
    def _validate_unique_steps(self, steps: Iterable[Dict[str, Any]]) -> None:
        seen: set[str] = set()
        for raw in steps:
            step_id = self._expect_str(raw, "id")
            if step_id in seen:
                raise RecipeError(f"Duplicate step id '{step_id}'")
            seen.add(step_id)

    def _build_adjacency(
        self,
        edges: Iterable[Dict[str, Any]],
        steps: Iterable[Dict[str, Any]],
    ) -> Dict[str, list[str]]:
        step_ids = {self._expect_str(raw, "id") for raw in steps}
        adjacency: Dict[str, list[str]] = {step_id: [] for step_id in step_ids}

        for edge in edges:
            if not isinstance(edge, dict):
                raise RecipeError("Edges must be objects")
            src = edge.get("from")
            dst = edge.get("to")
            if not isinstance(src, str) or not isinstance(dst, str):
                raise RecipeError("Edge requires 'from' and 'to' strings")
            if src not in step_ids:
                raise RecipeError(f"Edge references unknown step '{src}'")
            if dst not in step_ids:
                raise RecipeError(f"Edge references unknown step '{dst}'")
            adjacency.setdefault(src, []).append(dst)
        return adjacency

    def _validate_graph(
        self,
        entry: str,
        steps: Iterable[Dict[str, Any]],
        adjacency: Dict[str, list[str]],
    ) -> None:
        step_ids = {self._expect_str(raw, "id") for raw in steps}
        if entry not in step_ids:
            raise RecipeError(f"Entry step '{entry}' not defined")

        # Detect cycles via DFS
        visiting: set[str] = set()
        visited: set[str] = set()

        def dfs(node: str) -> None:
            if node in visiting:
                raise RecipeError(f"Cycle detected at step '{node}'")
            if node in visited:
                return
            visiting.add(node)
            for nxt in adjacency.get(node, []):
                dfs(nxt)
            visiting.remove(node)
            visited.add(node)

        dfs(entry)
        unreachable = step_ids - visited
        if unreachable:
            raise RecipeError(f"Unreachable step(s): {', '.join(sorted(unreachable))}")

    def _validate_config(
        self,
        step_id: str,
        op: Operation,
        config: Dict[str, Any],
        adjacency: Dict[str, list[str]],
    ) -> None:
        if op is Operation.SWITCH:
            cases = config.get("cases")
            if not isinstance(cases, dict) or not cases:
                raise RecipeError(f"Switch step '{step_id}' requires non-empty config.cases")
            default = config.get("default")
            if default is not None and not isinstance(default, str):
                raise RecipeError(f"Switch step '{step_id}' default must be a string")
            targets = set(adjacency.get(step_id, ()))
            case_targets = set(cases.values())
            if default:
                if default in cases:
                    case_targets.add(cases[default])
                else:
                    case_targets.add(default)
            missing = case_targets - targets
            if missing:
                raise RecipeError(f"Switch step '{step_id}' missing edge(s) for targets: {', '.join(sorted(missing))}")
        elif op is Operation.PARALLEL:
            branches = config.get("branches")
            if not isinstance(branches, list) or not all(isinstance(b, str) for b in branches):
                raise RecipeError(f"Parallel step '{step_id}' requires config.branches as list[str]")
            targets = set(adjacency.get(step_id, ()))
            missing = {branch for branch in branches if branch not in targets}
            if missing:
                raise RecipeError(
                    f"Parallel step '{step_id}' missing edge(s) for branches: {', '.join(sorted(missing))}"
                )
        elif op is Operation.FINISH:
            if adjacency.get(step_id):
                raise RecipeError(f"Finish step '{step_id}' cannot have outgoing edges")

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    def _expect_str(self, obj: Dict[str, Any], key: str) -> str:
        value = obj.get(key)
        if not isinstance(value, str) or not value:
            raise RecipeError(f"Field '{key}' must be a non-empty string")
        return value

    def _resolve_hook(self, path: Optional[str]):
        if not path:
            return None
        if not isinstance(path, str):
            raise RecipeError("Hook reference must be a string")
        module_name, _, attr = path.rpartition(".")
        if not module_name or not attr:
            raise RecipeError(f"Hook path '{path}' must include module and attribute")
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            raise RecipeError(f"Could not import module '{module_name}' for hook '{path}'") from exc
        if not hasattr(module, attr):
            raise RecipeError(f"Module '{module_name}' has no attribute '{attr}' for hook '{path}'")
        return getattr(module, attr)


__all__ = ["RecipeLoader", "RecipeError"]
