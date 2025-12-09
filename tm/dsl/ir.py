from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple, Union

from ._render import render_raw_node
from .parser import (
    DslParseError,
    ParsedDocument,
    RawMapping,
    RawMappingEntry,
    RawNode,
    RawScalar,
    RawSequence,
    SourceLocation,
    parse_pdl,
    parse_wdl,
)

"""Intermediate representations for the TraceMind DSL suite."""


@dataclass(frozen=True)
class SourceSpan:
    """Location information associated with IR nodes."""

    filename: Optional[str]
    line: int
    column: int

    @classmethod
    def from_location(cls, filename: Optional[str], location: SourceLocation) -> "SourceSpan":
        return cls(filename=filename, line=location.line, column=location.column)


# WDL IR models ----------------------------------------------------------------


@dataclass(frozen=True)
class WdlInput:
    name: str
    type_name: str
    location: SourceSpan


@dataclass(frozen=True)
class WdlArgument:
    name: str
    value: RawNode
    location: SourceSpan


@dataclass(frozen=True)
class WdlCallStep:
    step_id: str
    target: str
    args: Tuple[WdlArgument, ...]
    location: SourceSpan


@dataclass(frozen=True)
class WdlWhenStep:
    condition: str
    steps: Tuple[Union["WdlCallStep", "WdlWhenStep"], ...]
    location: SourceSpan


WdlStep = Union[WdlCallStep, WdlWhenStep]


@dataclass(frozen=True)
class WdlOutput:
    name: str
    value: RawNode
    location: SourceSpan


@dataclass(frozen=True)
class WdlTrigger:
    trigger_type: str
    config: Dict[str, object]
    location: SourceSpan


@dataclass(frozen=True)
class WdlWorkflow:
    version: str
    name: str
    inputs: Tuple[WdlInput, ...]
    steps: Tuple[WdlStep, ...]
    outputs: Tuple[WdlOutput, ...]
    triggers: Tuple[WdlTrigger, ...]
    location: SourceSpan


# PDL IR models ----------------------------------------------------------------


@dataclass(frozen=True)
class PdlArmField:
    name: str
    value: RawNode
    location: SourceSpan


@dataclass(frozen=True)
class PdlArm:
    name: str
    fields: Tuple[PdlArmField, ...]
    location: SourceSpan


@dataclass(frozen=True)
class PdlAssignment:
    target: str
    expression: str
    operator: str
    statement_id: Optional[str]
    location: SourceSpan


@dataclass(frozen=True)
class PdlChooseOption:
    name: str
    expression: str
    probability: Optional[str]
    location: SourceSpan


@dataclass(frozen=True)
class PdlChoose:
    options: Tuple[PdlChooseOption, ...]
    location: SourceSpan


@dataclass(frozen=True)
class PdlConditional:
    condition: str
    body: Tuple["PdlStatement", ...]
    else_body: Optional[Tuple["PdlStatement", ...]]
    location: SourceSpan


PdlStatement = Union[PdlAssignment, PdlChoose, PdlConditional]


@dataclass(frozen=True)
class PdlEmitField:
    name: str
    value: RawNode
    location: SourceSpan


@dataclass(frozen=True)
class PdlPolicy:
    version: str
    arms: Tuple[PdlArm, ...]
    epsilon: Optional[str]
    evaluate: Tuple[PdlStatement, ...]
    emit: Tuple[PdlEmitField, ...]
    location: SourceSpan


# Public helpers ---------------------------------------------------------------


def parse_wdl_document(text: str, *, filename: Optional[str] = None) -> WdlWorkflow:
    """Parse the given WDL text into a workflow IR."""
    document = parse_wdl(text, filename=filename)
    return build_wdl_ir(document)


def parse_pdl_document(text: str, *, filename: Optional[str] = None) -> PdlPolicy:
    """Parse the given PDL text into a policy IR."""
    document = parse_pdl(text, filename=filename)
    return build_pdl_ir(document)


def build_wdl_ir(document: ParsedDocument) -> WdlWorkflow:
    ctx = _Context(filename=document.filename)
    top = _mapping_to_dict(document.root, ctx)

    version_node = _require_scalar(top, "version", ctx, container_location=document.root.location)
    version = version_node.value.strip()
    if not version:
        raise _ctx_error(ctx, "Workflow version cannot be empty", version_node.location)

    name_node = _require_scalar(top, "workflow", ctx, container_location=document.root.location)
    workflow_name = name_node.value.strip()
    if not workflow_name:
        raise _ctx_error(ctx, "Workflow name cannot be empty", name_node.location)

    inputs_node = top.get("inputs")
    inputs: Tuple[WdlInput, ...] = ()
    if inputs_node is not None:
        inputs_mapping = _require_mapping(inputs_node, "inputs", ctx)
        inputs_list: List[WdlInput] = []
        for entry in inputs_mapping.entries:
            if entry.key is None:
                raise _ctx_error(ctx, "Input declarations must have a name", entry.key_location)
            scalar = _require_scalar_node(entry.value, ctx, hint="input type")
            inputs_list.append(
                WdlInput(
                    name=entry.key,
                    type_name=scalar.value.strip(),
                    location=_span(ctx, entry.key_location),
                )
            )
        inputs = tuple(inputs_list)

    outputs_node = top.get("outputs")
    outputs: Tuple[WdlOutput, ...] = ()
    if outputs_node is not None:
        outputs_mapping = _require_mapping(outputs_node, "outputs", ctx)
        outputs_list: List[WdlOutput] = []
        for entry in outputs_mapping.entries:
            if entry.key is None:
                raise _ctx_error(ctx, "Output declarations must have a name", entry.key_location)
            outputs_list.append(
                WdlOutput(
                    name=entry.key,
                    value=entry.value,
                    location=_span(ctx, entry.key_location),
                )
            )
        outputs = tuple(outputs_list)

    steps_node = top.get("steps")
    if steps_node is None:
        raise _ctx_error(ctx, "Workflow must define 'steps'", document.root.location)
    steps_sequence = _require_sequence(steps_node, "steps", ctx)
    steps = tuple(_parse_wdl_step(item, ctx) for item in steps_sequence.items)

    triggers_node = top.get("triggers")
    triggers: Tuple[WdlTrigger, ...] = ()
    if triggers_node is not None:
        triggers = tuple(_parse_wdl_triggers(triggers_node, ctx))

    return WdlWorkflow(
        version=version,
        name=workflow_name,
        inputs=inputs,
        steps=steps,
        outputs=outputs,
        triggers=triggers,
        location=_span(ctx, document.root.location),
    )


def build_pdl_ir(document: ParsedDocument) -> PdlPolicy:
    ctx = _Context(filename=document.filename)
    top = _mapping_to_dict(document.root, ctx)

    version_node = _require_scalar(top, "version", ctx, container_location=document.root.location)
    version = version_node.value.strip()
    if not version:
        raise _ctx_error(ctx, "Policy version cannot be empty", version_node.location)

    arms_node = top.get("arms")
    if arms_node is None:
        raise _ctx_error(ctx, "Policy must define 'arms'", document.root.location)
    arms_mapping = _require_mapping(arms_node, "arms", ctx)
    arms: List[PdlArm] = []
    for entry in arms_mapping.entries:
        if entry.key is None:
            raise _ctx_error(ctx, "Arm declarations must have a name", entry.key_location)
        arm_fields_mapping = _require_mapping(entry.value, f"arm '{entry.key}'", ctx)
        fields: List[PdlArmField] = []
        for field in arm_fields_mapping.entries:
            if field.key is None:
                raise _ctx_error(ctx, "Arm fields must have a name", field.key_location)
            fields.append(
                PdlArmField(
                    name=field.key,
                    value=field.value,
                    location=_span(ctx, field.key_location),
                )
            )
        arms.append(
            PdlArm(
                name=entry.key,
                fields=tuple(fields),
                location=_span(ctx, entry.key_location),
            )
        )

    epsilon_node = top.get("epsilon")
    epsilon: Optional[str] = None
    if epsilon_node is not None:
        epsilon_scalar = _require_scalar_node(epsilon_node, ctx, hint="epsilon value")
        epsilon = epsilon_scalar.value.strip()

    evaluate_node = top.get("evaluate")
    if evaluate_node is None:
        raise _ctx_error(ctx, "Policy must define 'evaluate'", document.root.location)
    evaluate_mapping = _require_mapping(evaluate_node, "evaluate", ctx)
    evaluate_statements = tuple(_parse_pdl_statements(evaluate_mapping.entries, ctx))

    emit_node = top.get("emit")
    if emit_node is None:
        raise _ctx_error(ctx, "Policy must define 'emit'", document.root.location)
    emit_mapping = _require_mapping(emit_node, "emit", ctx)
    emit_fields: List[PdlEmitField] = []
    for entry in emit_mapping.entries:
        if entry.key is None:
            raise _ctx_error(ctx, "Emit entries must have a name", entry.key_location)
        emit_fields.append(
            PdlEmitField(
                name=entry.key,
                value=entry.value,
                location=_span(ctx, entry.key_location),
            )
        )

    return PdlPolicy(
        version=version,
        arms=tuple(arms),
        epsilon=epsilon,
        evaluate=evaluate_statements,
        emit=tuple(emit_fields),
        location=_span(ctx, document.root.location),
    )


# Internal helpers -------------------------------------------------------------


@dataclass(frozen=True)
class _Context:
    filename: Optional[str]


def _span(ctx: _Context, location: SourceLocation) -> SourceSpan:
    return SourceSpan.from_location(ctx.filename, location)


def _ctx_error(ctx: _Context, message: str, location: SourceLocation) -> DslParseError:
    return DslParseError(message, location=location, filename=ctx.filename)


def _mapping_to_dict(mapping: RawMapping, ctx: _Context) -> dict[str, RawNode]:
    result: dict[str, RawNode] = {}
    for entry in mapping.entries:
        if entry.key is None:
            raise _ctx_error(ctx, "Unexpected statement in mapping", entry.key_location)
        if entry.key in result:
            raise _ctx_error(ctx, f"Duplicate key '{entry.key}'", entry.key_location)
        result[entry.key] = entry.value
    return result


def _require_scalar(
    mapping: dict[str, RawNode],
    key: str,
    ctx: _Context,
    *,
    container_location: SourceLocation,
) -> RawScalar:
    node = mapping.get(key)
    if node is None:
        raise _ctx_error(ctx, f"Missing required key '{key}'", container_location)
    return _require_scalar_node(node, ctx, hint=key)


def _require_scalar_node(node: RawNode, ctx: _Context, *, hint: str) -> RawScalar:
    if isinstance(node, RawScalar):
        return node
    raise _ctx_error(ctx, f"Expected scalar for {hint}", _node_location(node))


def _require_mapping(node: RawNode, label: str, ctx: _Context) -> RawMapping:
    if isinstance(node, RawMapping):
        return node
    raise _ctx_error(ctx, f"Expected mapping for {label}", _node_location(node))


def _require_sequence(node: RawNode, label: str, ctx: _Context) -> RawSequence:
    if isinstance(node, RawSequence):
        return node
    raise _ctx_error(ctx, f"Expected list for {label}", _node_location(node))


def _parse_wdl_step(node: RawNode, ctx: _Context) -> WdlStep:
    if not isinstance(node, RawMapping):
        raise _ctx_error(ctx, "Step must be a mapping entry", _node_location(node))
    if not node.entries:
        raise _ctx_error(ctx, "Empty step declaration", node.location)

    entry = next((item for item in node.entries if item.key is not None), None)
    if entry is None:
        raise _ctx_error(ctx, "Step declaration missing identifier", node.location)
    key = entry.key
    assert key is not None

    if key.startswith("when "):
        condition = key[len("when ") :].strip()
        if not condition:
            raise _ctx_error(ctx, "When step requires a condition", entry.key_location)
        nested_steps = _parse_wdl_step_block(entry.value, ctx)
        return WdlWhenStep(
            condition=condition,
            steps=nested_steps,
            location=_span(ctx, entry.key_location),
        )

    step_id, target = _parse_wdl_call_header(key, ctx, entry.key_location)
    args_mapping = _require_mapping(entry.value, f"step '{step_id}' arguments", ctx)
    args: List[WdlArgument] = []
    for arg_entry in args_mapping.entries:
        if arg_entry.key is None:
            raise _ctx_error(ctx, "Argument name cannot be omitted", arg_entry.key_location)
        args.append(
            WdlArgument(
                name=arg_entry.key,
                value=arg_entry.value,
                location=_span(ctx, arg_entry.key_location),
            )
        )
    return WdlCallStep(
        step_id=step_id,
        target=target,
        args=tuple(args),
        location=_span(ctx, entry.key_location),
    )


def _parse_wdl_step_block(node: RawNode, ctx: _Context) -> Tuple[WdlStep, ...]:
    if isinstance(node, RawSequence):
        return tuple(_parse_wdl_step(item, ctx) for item in node.items)
    if isinstance(node, RawMapping):
        steps: List[WdlStep] = []
        for entry in node.entries:
            if entry.key is None:
                raise _ctx_error(ctx, "Step declarations require a name", entry.key_location)
            pseudo_mapping = RawMapping(entries=(entry,), location=node.location)
            steps.append(_parse_wdl_step(pseudo_mapping, ctx))
        return tuple(steps)
    raise _ctx_error(ctx, "When body must be a list or mapping", _node_location(node))


def _parse_wdl_call_header(header: str, ctx: _Context, location: SourceLocation) -> Tuple[str, str]:
    if "(" not in header or not header.endswith(")"):
        raise _ctx_error(ctx, "Call step must follow 'name(target)' format", location)
    name, target = header.split("(", 1)
    step_id = name.strip()
    call_target = target[:-1].strip()
    if not step_id:
        raise _ctx_error(ctx, "Step identifier cannot be empty", location)
    if not call_target:
        raise _ctx_error(ctx, "Call target cannot be empty", location)
    return step_id, call_target


def _parse_pdl_statements(entries: Sequence[RawMappingEntry], ctx: _Context) -> List[PdlStatement]:
    statements: List[PdlStatement] = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        if entry.key is None:
            scalar = _require_scalar_node(entry.value, ctx, hint="statement")
            statements.append(_parse_pdl_assignment(scalar, ctx))
            index += 1
            continue

        key = entry.key
        if key.startswith("if "):
            condition = key[3:].strip()
            if not condition:
                raise _ctx_error(ctx, "If statement requires a condition", entry.key_location)
            body_node = entry.value
            body_statements = _parse_pdl_block(body_node, ctx)
            else_body: Optional[Tuple[PdlStatement, ...]] = None
            if index + 1 < len(entries) and entries[index + 1].key == "else":
                else_entry = entries[index + 1]
                else_body = tuple(_parse_pdl_block(else_entry.value, ctx))
                index += 1
            statements.append(
                PdlConditional(
                    condition=condition,
                    body=tuple(body_statements),
                    else_body=else_body,
                    location=_span(ctx, entry.key_location),
                )
            )
            index += 1
            continue

        if key == "else":
            raise _ctx_error(ctx, "Unexpected 'else' without matching 'if'", entry.key_location)

        if key == "choose":
            choose_mapping = _require_mapping(entry.value, "choose", ctx)
            options: List[PdlChooseOption] = []
            for option in choose_mapping.entries:
                if option.key is None:
                    raise _ctx_error(ctx, "Choose options must have a name", option.key_location)
                option_scalar = _require_scalar_node(option.value, ctx, hint="choose option")
                expression, probability = _split_probability(option_scalar.value.strip())
                options.append(
                    PdlChooseOption(
                        name=option.key,
                        expression=expression,
                        probability=probability,
                        location=_span(ctx, option.key_location),
                    )
                )
            statements.append(PdlChoose(options=tuple(options), location=_span(ctx, entry.key_location)))
            index += 1
            continue

        # Default fallback: treat as assignment-like statement with labelled key.
        scalar_value = _require_scalar_node(entry.value, ctx, hint=f"statement '{key}'")
        assignment = _parse_pdl_assignment(scalar_value, ctx, statement_id=key)
        statements.append(assignment)
        index += 1
    return statements


def _parse_pdl_block(node: RawNode, ctx: _Context) -> List[PdlStatement]:
    if isinstance(node, RawMapping):
        return _parse_pdl_statements(node.entries, ctx)
    if isinstance(node, RawSequence):
        statements: List[PdlStatement] = []
        for item in node.items:
            if isinstance(item, RawMapping):
                statements.extend(_parse_pdl_statements(item.entries, ctx))
            elif isinstance(item, RawScalar):
                statements.append(_parse_pdl_assignment(item, ctx))
            else:
                raise _ctx_error(ctx, "Unsupported statement in block", _node_location(item))
        return statements
    raise _ctx_error(ctx, "Expected block of statements", _node_location(node))


def _parse_pdl_assignment(
    scalar: RawScalar,
    ctx: _Context,
    *,
    statement_id: Optional[str] = None,
) -> PdlAssignment:
    text = scalar.value.strip()
    operator = ":=" if ":=" in text else "="
    parts = text.split(operator, 1)
    if len(parts) != 2:
        raise _ctx_error(ctx, "Assignment must contain '=' or ':='", scalar.location)
    target = parts[0].strip()
    expression = parts[1].strip()
    if not target:
        raise _ctx_error(ctx, "Assignment target cannot be empty", scalar.location)
    if not expression:
        raise _ctx_error(ctx, "Assignment expression cannot be empty", scalar.location)
    return PdlAssignment(
        target=target,
        expression=expression,
        operator=operator,
        statement_id=statement_id,
        location=_span(ctx, scalar.location),
    )


def _split_probability(expression: str) -> Tuple[str, Optional[str]]:
    marker = " with p="
    if marker not in expression:
        return expression, None
    base, remainder = expression.split(marker, 1)
    probability = remainder.strip()
    return base.strip(), probability or None


def _node_location(node: RawNode) -> SourceLocation:
    if isinstance(node, RawScalar):
        return node.location
    if isinstance(node, RawMapping):
        return node.location
    if isinstance(node, RawSequence):
        return node.location
    raise TypeError(f"Unsupported node type: {type(node)!r}")


def _require_sequence_or_mapping(node: RawNode, label: str, ctx: _Context) -> RawNode:
    if isinstance(node, (RawSequence, RawMapping)):
        return node
    raise _ctx_error(ctx, f"Expected list or mapping for {label}", _node_location(node))


def _parse_wdl_triggers(node: RawNode, ctx: _Context) -> List[WdlTrigger]:
    normalized = _require_sequence_or_mapping(node, "triggers", ctx)
    triggers: List[WdlTrigger] = []
    if isinstance(normalized, RawSequence):
        for item in normalized.items:
            if not isinstance(item, RawMapping):
                raise _ctx_error(ctx, "Trigger entries must be mappings", _node_location(item))
            triggers.extend(_parse_trigger_mapping(item, ctx))
    elif isinstance(normalized, RawMapping):
        triggers.extend(_parse_trigger_mapping(normalized, ctx))
    return triggers


def _parse_trigger_mapping(mapping: RawMapping, ctx: _Context) -> List[WdlTrigger]:
    triggers: List[WdlTrigger] = []
    explicit_type = next((entry for entry in mapping.entries if entry.key == "type"), None)
    if explicit_type is not None:
        trigger_type = _expect_scalar_text(explicit_type.value, ctx, "trigger type")
        config: Dict[str, object] = {}
        for entry in mapping.entries:
            if entry is explicit_type or entry.key is None:
                continue
            config[entry.key] = render_raw_node(entry.value)
        triggers.append(
            WdlTrigger(
                trigger_type=trigger_type,
                config=config,
                location=SourceSpan.from_location(ctx.filename, explicit_type.key_location),
            )
        )
        return triggers

    for entry in mapping.entries:
        if entry.key is None:
            continue
        config_obj = _normalize_config(render_raw_node(entry.value))
        if not isinstance(config_obj, dict):
            config_obj = {"value": config_obj}
        triggers.append(
            WdlTrigger(
                trigger_type=entry.key,
                config=config_obj,
                location=SourceSpan.from_location(ctx.filename, entry.key_location),
            )
        )
    return triggers


def _expect_scalar_text(node: RawNode, ctx: _Context, label: str) -> str:
    if isinstance(node, RawScalar):
        raw = node.value.strip()
        normalized = _normalize_config(raw)
        return normalized if isinstance(normalized, str) else raw
    raise _ctx_error(ctx, f"Expected scalar text for {label}", _node_location(node))


def _normalize_config(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        if (stripped.startswith('"') and stripped.endswith('"')) or (
            stripped.startswith("'") and stripped.endswith("'")
        ):
            try:
                return ast.literal_eval(stripped)
            except Exception:
                return stripped
        return stripped
    if isinstance(value, list):
        return [_normalize_config(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_config(item) for key, item in value.items()}
    return value


__all__ = [
    "SourceSpan",
    "WdlArgument",
    "WdlCallStep",
    "WdlInput",
    "WdlOutput",
    "WdlStep",
    "WdlWhenStep",
    "WdlWorkflow",
    "PdlArm",
    "PdlArmField",
    "PdlAssignment",
    "PdlChoose",
    "PdlChooseOption",
    "PdlConditional",
    "PdlEmitField",
    "PdlPolicy",
    "PdlStatement",
    "build_pdl_ir",
    "build_wdl_ir",
    "parse_pdl_document",
    "parse_wdl_document",
]
