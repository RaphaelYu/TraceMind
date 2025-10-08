from __future__ import annotations
from typing import Any, List, Tuple

Path = Tuple[Any, ...]


def parse(expr: str) -> List[str]:
    toks: List[str] = []
    buf = ""
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch == ".":
            if buf:
                toks.append(buf)
                buf = ""
            i += 1
        elif ch == "[":
            if buf:
                toks.append(buf)
                buf = ""
            j = expr.find("]", i)
            if j < 0:
                raise ValueError(f"Unclosed '[' in selector: {expr}")
            toks.append(expr[i : j + 1])
            i = j + 1
        else:
            buf += ch
            i += 1
    if buf:
        toks.append(buf)
    return toks


def match(expr: str, path: Path) -> bool:
    """Match path against selector expr. Supports '*', '[]', and concrete indices '[3]'."""
    toks = parse(expr)
    pi = 0
    for tk in toks:
        if pi >= len(path):
            return False
        v = path[pi]
        if tk == "*":
            pi += 1
        elif tk == "[]":
            if not isinstance(v, int):
                return False
            pi += 1
        elif tk.startswith("[") and tk.endswith("]"):
            inner = tk[1:-1]
            if inner == "":  # treat as []
                if not isinstance(v, int):
                    return False
                pi += 1
            else:
                try:
                    idx = int(inner)
                except ValueError:
                    return False
                if v != idx:
                    return False
                pi += 1
        else:
            if v != tk:
                return False
            pi += 1
    return pi == len(path)
