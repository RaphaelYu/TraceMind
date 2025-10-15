from __future__ import annotations

import json
import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Mapping, Optional

_POLICY_CACHE: Dict[str, Dict[str, Any]] = {}


def call(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    state = _ensure_state(state)
    step_name = ctx.get("step")
    config = ctx.get("config", {})
    call_spec = config.get("call") if isinstance(config, Mapping) else None
    if not isinstance(call_spec, Mapping):
        raise RuntimeError("Call step missing configuration")

    target = call_spec.get("target")
    args_spec = call_spec.get("args", {})
    evaluated_args = _evaluate_value(args_spec, state)

    if isinstance(target, str):
        handler = _HANDLERS.get(target, _default_handler)
    else:
        handler = _default_handler

    result = handler(ctx, state, evaluated_args)
    if not isinstance(result, dict):
        raise RuntimeError(f"Handler for '{target}' must return a dict")
    if isinstance(step_name, str):
        state["steps"][step_name] = result
    state["current"] = result
    return state


def switch(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    # Switch steps are evaluated by the runtime via edges; we just mirror state.
    state = _ensure_state(state)
    state["current"] = {"config": dict(ctx.get("config", {}))}
    return state


def emit_outputs(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    state = _ensure_state(state)
    config = ctx.get("config", {})
    outputs_spec = config.get("outputs", {})
    evaluated = _evaluate_value(outputs_spec, state)
    if not isinstance(evaluated, dict):
        raise RuntimeError("Outputs step must evaluate to a mapping")
    state["outputs"] = evaluated
    state["current"] = evaluated
    return state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ensure_state(state: Dict[str, Any]) -> Dict[str, Any]:
    if "steps" not in state or not isinstance(state.get("steps"), dict):
        inputs = dict(state)
        state.clear()
        state["inputs"] = inputs
        state["steps"] = {}
        state["current"] = {}
    else:
        state.setdefault("inputs", {})
        state.setdefault("current", {})
    return state


def _evaluate_value(value: Any, state: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("$input."):
            return _lookup_path(state.get("inputs", {}), text[len("$input.") :])
        if text.startswith("$step."):
            step_path = text[len("$step.") :]
            step_name, _, remainder = step_path.partition(".")
            step_data = state.get("steps", {}).get(step_name, {})
            if remainder:
                return _lookup_path(step_data, remainder)
            return step_data
        try:
            return ast.literal_eval(text)
        except Exception:
            current = state.get("current", {})
            return current.get(text, text)
    if isinstance(value, list):
        return [_evaluate_value(item, state) for item in value]
    if isinstance(value, dict):
        return {key: _evaluate_value(val, state) for key, val in value.items()}
    return value


def _lookup_path(root: Any, dotted: str) -> Any:
    cur = root
    for part in dotted.split("."):

        if isinstance(cur, Mapping):
            cur = cur.get(part)
        else:
            return None
    return cur


# ---------------------------------------------------------------------------
# Call handlers
# ---------------------------------------------------------------------------
def _default_handler(ctx: Dict[str, Any], state: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    target = ctx.get("config", {}).get("call", {}).get("target")
    return {"target": target, "args": args}


def _handle_opcua_read(ctx: Dict[str, Any], state: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    endpoint = args.get("endpoint")
    node_ids = args.get("node_ids", [])
    values: Dict[str, Any] = {}
    if isinstance(node_ids, list):
        for node in node_ids:
            values[str(node)] = 80.0
    return {"endpoint": endpoint, "values": values}


def _handle_opcua_write(ctx: Dict[str, Any], state: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    endpoint = args.get("endpoint")
    node_id = args.get("node_id")
    value = args.get("value")
    return {"endpoint": endpoint, "node_id": node_id, "value": value, "status": "ok"}


def _handle_policy_apply(ctx: Dict[str, Any], state: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    config = ctx.get("config", {})
    policy_path = config.get("policy_ref")
    policy_id = config.get("policy_id")
    try:
        policy = _load_policy(policy_path)
    except Exception:
        return {"action": "NONE", "policy_id": policy_id, "values": args.get("values")}
    runner = _PolicyRunner(policy, policy_id)
    return runner.run(args)


_HANDLERS = {
    "opcua.read": _handle_opcua_read,
    "opcua.write": _handle_opcua_write,
    "policy.apply": _handle_policy_apply,
}


# ---------------------------------------------------------------------------
# Policy evaluation
# ---------------------------------------------------------------------------
class _PolicyRunner:
    def __init__(self, policy_data: Dict[str, Any], policy_id: Optional[str]) -> None:
        policy = policy_data.get("policy", {})
        params = policy.get("params", {})
        arms = params.get("arms", {})
        first_arm = next(iter(arms.values())) if isinstance(arms, dict) and arms else {}
        self._arm_struct = _to_namespace(first_arm)
        self._evaluate = params.get("evaluate", [])
        self._emit = params.get("emit", {})
        self._epsilon = _as_float(params.get("epsilon"))
        self._policy_id = policy_id or policy.get("id")
        self._scope: Dict[str, Any] = {}
        self._env: Dict[str, Any] = {
            "arms": SimpleNamespace(active=self._arm_struct),
            "epsilon": self._epsilon,
            "coalesce": _fn_coalesce,
            "first_numeric": _fn_first_numeric,
            "random": _fn_random_choice,
        }

    def run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        self._scope.clear()
        self._env["values"] = args.get("values")
        for stmt in self._evaluate:
            self._execute_statement(stmt)
        outputs = _evaluate_policy_value(self._emit, self._scope, self._env)
        if isinstance(outputs, dict):
            outputs.setdefault("policy_id", self._policy_id)
        return outputs if isinstance(outputs, dict) else {"result": outputs, "policy_id": self._policy_id}

    def _execute_statement(self, stmt: Mapping[str, Any]) -> None:
        stmt_type = stmt.get("type")
        if stmt_type == "assignment":
            target = stmt.get("target")
            expr = stmt.get("expression")
            if isinstance(target, str) and isinstance(expr, str):
                value = self._eval_expr(expr)
                self._scope[target] = value
        elif stmt_type == "if":
            condition = stmt.get("condition")
            if isinstance(condition, str) and self._is_truthy(self._eval_expr(condition)):
                for child in stmt.get("then", []):
                    if isinstance(child, Mapping):
                        self._execute_statement(child)
            else:
                for child in stmt.get("else", []) or []:
                    if isinstance(child, Mapping):
                        self._execute_statement(child)
        elif stmt_type == "choose":
            options = stmt.get("options", [])
            for option in options:
                if not isinstance(option, Mapping):
                    continue
                expr = option.get("expression")
                if not isinstance(expr, str):
                    continue
                self._execute_assignment_text(expr)
                break

    def _execute_assignment_text(self, text: str) -> None:
        if ":=" in text:
            target, expr = text.split(":=", 1)
        else:
            target, expr = text.split("=", 1)
        target = target.strip()
        expr = expr.strip()
        if not target:
            return
        value = self._eval_expr(expr)
        self._scope[target] = value

    def _eval_expr(self, expr: str) -> Any:
        locals_env = dict(self._scope)
        locals_env.update(self._env)
        try:
            return eval(expr, {"__builtins__": {}}, locals_env)
        except Exception:
            return expr

    @staticmethod
    def _is_truthy(value: Any) -> bool:
        return bool(value)


def _evaluate_policy_value(value: Any, scope: Dict[str, Any], env: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        try:
            return eval(value, {"__builtins__": {}}, {**env, **scope})
        except Exception:
            return value
    if isinstance(value, list):
        return [_evaluate_policy_value(item, scope, env) for item in value]
    if isinstance(value, dict):
        return {key: _evaluate_policy_value(val, scope, env) for key, val in value.items()}
    return value


def _to_namespace(value: Any) -> Any:
    if isinstance(value, Mapping):
        return SimpleNamespace(**{k: _to_namespace(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_to_namespace(item) for item in value]
    return value


def _fn_coalesce(*args: Any) -> Any:
    for arg in args:
        if arg not in (None, "", [], {}):
            return arg
    return None


def _fn_first_numeric(values: Any) -> Optional[float]:
    if isinstance(values, Mapping):
        for item in values.values():
            number = _as_float(item)
            if number is not None:
                return number
    if isinstance(values, list):
        for item in values:
            number = _as_float(item)
            if number is not None:
                return number
    return None


def _fn_random_choice(options: Any) -> Any:
    if isinstance(options, list) and options:
        return options[0]
    return None


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _load_policy(path: Any) -> Dict[str, Any]:
    if not isinstance(path, str):
        raise RuntimeError("policy.apply step requires policy_ref path")
    cached = _POLICY_CACHE.get(path)
    if cached is not None:
        return cached
    resolved = Path(path)
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Policy file '{path}' must contain an object")
    _POLICY_CACHE[path] = data
    return data


__all__ = ["call", "switch", "emit_outputs"]
