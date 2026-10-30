"""Narrowing helpers for untrusted JSON (mirrors typescript/src/json.ts)."""
from __future__ import annotations

import math
from typing import Any


def as_list(value: Any) -> list[Any]:
    """The value if it is a JSON array, otherwise []. Strings and objects are never iterated."""
    return value if isinstance(value, list) else []


def is_int(value: Any) -> bool:
    """A JSON integer. Booleans are not numbers, unlike Python's ``isinstance(True, int)``."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value: Any) -> bool:
    """A finite JSON number (booleans excluded)."""
    return is_int(value) or (isinstance(value, float) and math.isfinite(value))
