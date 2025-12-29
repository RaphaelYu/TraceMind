from __future__ import annotations

import importlib
import importlib.util
from typing import Any


def import_yaml() -> Any | None:
    spec = importlib.util.find_spec("yaml")
    if spec is None:
        return None
    return importlib.import_module("yaml")
