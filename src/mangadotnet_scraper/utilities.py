from collections.abc import Mapping
from typing import Any


def clean_string(value: str) -> str:
    return value.replace("\u200f", "").strip("\r").strip("\n").strip()


def dict_get_recursive(obj: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    try:
        result = obj

        for key in keys:
            result = result[key]

        return result
    except KeyError:
        return default
