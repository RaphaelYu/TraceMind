from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union

"""
Parsing entry-points for the TraceMind DSL suite.

This module will provide the public ``parse_wdl`` and ``parse_pdl`` functions
used by higher-level tooling (lint, compile, plan).  At this stage only the
error container and parser scaffolding are defined; concrete implementations
will arrive in subsequent steps of the rollout.
"""


@dataclass(frozen=True)
class SourceLocation:
    """Represents a 1-based source location within a DSL document."""

    line: int
    column: int


@dataclass(frozen=True)
class DslParseError(Exception):
    """Raised when the DSL parser cannot interpret the provided text."""

    message: str
    location: Optional[SourceLocation] = None
    filename: Optional[str] = None

    def __str__(self) -> str:  # pragma: no cover - trivial
        prefix = ""
        if self.filename:
            prefix = f"{self.filename}: "
        if self.location:
            prefix += f"{self.location.line}:{self.location.column}: "
        return f"{prefix}{self.message}"


@dataclass(frozen=True)
class RawScalar:
    """Scalar literal captured during parsing."""

    value: str
    location: SourceLocation


@dataclass(frozen=True)
class RawMappingEntry:
    """Key/value association within a mapping."""

    key: Optional[str]
    key_location: SourceLocation
    value: "RawNode"


@dataclass(frozen=True)
class RawMapping:
    """Mapping node (dictionary) in the raw parse tree."""

    entries: Tuple[RawMappingEntry, ...]
    location: SourceLocation


@dataclass(frozen=True)
class RawSequence:
    """Sequence node (list) in the raw parse tree."""

    items: Tuple["RawNode", ...]
    location: SourceLocation


RawNode = Union[RawScalar, RawMapping, RawSequence]


@dataclass(frozen=True)
class ParsedDocument:
    """Result of parsing a DSL document."""

    root: RawMapping
    filename: Optional[str] = None


def parse_wdl(text: str, *, filename: str | None = None) -> ParsedDocument:
    """Parse a WDL (Workflow-DSL) document."""
    return ParsedDocument(
        root=_parse_document(text, filename=filename),
        filename=filename,
    )


def parse_pdl(text: str, *, filename: str | None = None) -> ParsedDocument:
    """Parse a PDL (Policy-DSL) document."""
    return ParsedDocument(
        root=_parse_document(text, filename=filename),
        filename=filename,
    )


@dataclass(frozen=True)
class _Line:
    number: int
    indent: int
    content: str
    raw: str


def _parse_document(text: str, *, filename: str | None) -> RawMapping:
    lines = _prepare_lines(text, filename=filename)
    if not lines:
        raise DslParseError("Document is empty", filename=filename)
    first_indent = lines[0].indent
    if first_indent != 0:
        raise _error(
            "Document must start at the top indentation level",
            line=lines[0],
            column=lines[0].indent + 1,
            filename=filename,
        )
    root, next_index = _parse_mapping(lines, 0, expected_indent=0, filename=filename)
    if next_index != len(lines):
        extra = lines[next_index]
        raise _error(
            "Unexpected content after document body",
            line=extra,
            column=extra.indent + 1,
            filename=filename,
        )
    return root


def _prepare_lines(text: str, *, filename: str | None) -> List[_Line]:
    processed: List[_Line] = []
    for idx, raw_line in enumerate(text.splitlines()):
        line_no = idx + 1
        current = raw_line.rstrip("\r\n")
        if not current.strip():
            continue  # skip blank lines
        indent_fragment = current[: len(current) - len(current.lstrip(" \t"))]
        if "\t" in indent_fragment:
            raise DslParseError(
                "Tabs are not allowed for indentation",
                location=SourceLocation(line_no, indent_fragment.index("\t") + 1),
                filename=filename,
            )
        indent = len(indent_fragment)
        content = current[indent:]
        if not content or content.lstrip().startswith("#"):
            continue
        processed.append(
            _Line(
                number=line_no,
                indent=indent,
                content=content,
                raw=current,
            )
        )
    return processed


def _parse_mapping(
    lines: Sequence[_Line],
    index: int,
    *,
    expected_indent: int,
    filename: str | None,
) -> Tuple[RawMapping, int]:
    entries: List[RawMappingEntry] = []
    start_line = lines[index]
    location = SourceLocation(start_line.number, start_line.indent + 1)
    cur = index
    while cur < len(lines):
        line = lines[cur]
        if line.indent < expected_indent:
            break
        if line.indent > expected_indent:
            raise _error(
                "Unexpected indentation (expected begin of mapping entry)",
                line=line,
                column=line.indent + 1,
                filename=filename,
            )
        if line.content.startswith("- "):
            raise _error(
                "List item not allowed in mapping context",
                line=line,
                column=line.indent + 1,
                filename=filename,
            )
        separator_index = _find_mapping_separator(line.content)
        value_node: RawNode
        if separator_index is None:
            entry_location = SourceLocation(line.number, line.indent + 1)
            value_node = RawScalar(value=line.content, location=entry_location)
            entries.append(
                RawMappingEntry(
                    key=None,
                    key_location=entry_location,
                    value=value_node,
                )
            )
            cur += 1
            continue

        key_text = line.content[:separator_index]
        raw_value = line.content[separator_index + 1 :]
        key = key_text.strip()
        if not key:
            raise _error("Key cannot be empty", line=line, column=line.indent + 1, filename=filename)
        key_column = line.indent + line.content[:separator_index].find(key) + 1
        key_location = SourceLocation(line.number, key_column)

        value_text = raw_value.lstrip()
        value_column = line.indent + separator_index + 2 + (len(raw_value) - len(value_text))
        if value_text:
            value_node = RawScalar(
                value=value_text,
                location=SourceLocation(line.number, value_column),
            )
            cur += 1
        else:
            if cur + 1 >= len(lines):
                value_node = RawMapping(entries=tuple(), location=SourceLocation(line.number, value_column))
                cur += 1
            else:
                next_line = lines[cur + 1]
                if next_line.indent <= expected_indent:
                    value_node = RawMapping(entries=tuple(), location=SourceLocation(line.number, value_column))
                    cur += 1
                elif next_line.content.startswith("- "):
                    sequence, new_index = _parse_sequence(
                        lines,
                        cur + 1,
                        expected_indent=next_line.indent,
                        filename=filename,
                    )
                    value_node = sequence
                    cur = new_index
                else:
                    mapping_child, new_index = _parse_mapping(
                        lines,
                        cur + 1,
                        expected_indent=next_line.indent,
                        filename=filename,
                    )
                    value_node = mapping_child
                    cur = new_index
        entries.append(RawMappingEntry(key=key, key_location=key_location, value=value_node))
    return RawMapping(entries=tuple(entries), location=location), cur


def _parse_sequence(
    lines: Sequence[_Line],
    index: int,
    *,
    expected_indent: int,
    filename: str | None,
) -> Tuple[RawSequence, int]:
    items: List[RawNode] = []
    if index >= len(lines):
        raise _error("Expected list item", line=lines[index - 1], column=lines[index - 1].indent + 1, filename=filename)
    start_line = lines[index]
    location = SourceLocation(start_line.number, start_line.indent + 1)
    cur = index
    while cur < len(lines):
        line = lines[cur]
        if line.indent < expected_indent:
            break
        if line.indent > expected_indent:
            raise _error(
                "Unexpected indentation within list item",
                line=line,
                column=line.indent + 1,
                filename=filename,
            )
        if not line.content.startswith("- "):
            raise _error(
                "Expected '-' to start list item",
                line=line,
                column=line.indent + 1,
                filename=filename,
            )
        rest = line.content[2:]
        raw_value = rest
        value_text = raw_value.lstrip()
        value_column = line.indent + 3 + (len(raw_value) - len(value_text))
        cur += 1

        value_node: RawNode
        if not value_text:
            if cur >= len(lines):
                raise _error(
                    "Expected indented block after list item",
                    line=line,
                    column=line.indent + 1,
                    filename=filename,
                )
            next_line = lines[cur]
            if next_line.indent <= expected_indent:
                raise _error(
                    "Expected indented block after list item",
                    line=line,
                    column=line.indent + 1,
                    filename=filename,
                )
            if next_line.content.startswith("- "):
                value_node, cur = _parse_sequence(
                    lines,
                    cur,
                    expected_indent=next_line.indent,
                    filename=filename,
                )
            else:
                value_node, cur = _parse_mapping(
                    lines,
                    cur,
                    expected_indent=next_line.indent,
                    filename=filename,
                )
        elif value_text.endswith(":"):
            key_text = value_text[:-1].rstrip()
            if not key_text:
                raise _error(
                    "Empty key in list item mapping",
                    line=line,
                    column=line.indent + 1,
                    filename=filename,
                )
            key_location = SourceLocation(line.number, value_column)
            nested: RawNode
            if cur >= len(lines) or lines[cur].indent <= expected_indent:
                nested = RawMapping(entries=tuple(), location=SourceLocation(line.number, value_column))
            else:
                next_line = lines[cur]
                if next_line.content.startswith("- "):
                    nested, cur = _parse_sequence(
                        lines,
                        cur,
                        expected_indent=next_line.indent,
                        filename=filename,
                    )
                else:
                    nested, cur = _parse_mapping(
                        lines,
                        cur,
                        expected_indent=next_line.indent,
                        filename=filename,
                    )
            nested_node: RawNode = nested
            value_node = RawMapping(
                entries=(
                    RawMappingEntry(
                        key=key_text,
                        key_location=key_location,
                        value=nested_node,
                    ),
                ),
                location=SourceLocation(line.number, line.indent + 1),
            )
        else:
            value_node = RawScalar(value=value_text, location=SourceLocation(line.number, value_column))
        items.append(value_node)
    return RawSequence(items=tuple(items), location=location), cur


def _find_mapping_separator(content: str) -> Optional[int]:
    """Return the index of the mapping separator ':' if present."""
    in_single = False
    in_double = False
    escape_next = False
    for idx, ch in enumerate(content):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            continue
        if in_single or in_double:
            continue
        if ch != ":":
            continue
        next_char = content[idx + 1] if idx + 1 < len(content) else ""
        if next_char == "=":
            continue
        return idx
    return None


def _error(message: str, *, line: _Line, column: int, filename: str | None) -> DslParseError:
    column = max(1, column)
    return DslParseError(
        message,
        location=SourceLocation(line.number, column),
        filename=filename,
    )
