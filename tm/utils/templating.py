from __future__ import annotations
import re
from typing import Mapping, Any

_PATTERN = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")


def render_template(template: str, vars: Mapping[str, Any]) -> str:
    def _sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in vars:
            raise KeyError(f"missing template variable: {key}")
        val = vars[key]
        return str(val)

    return _PATTERN.sub(_sub, template)
