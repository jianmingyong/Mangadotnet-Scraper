from collections.abc import Mapping
from typing import Any, cast


def clean_string(value: str) -> str:
    return value.replace("\u200f", "").strip("\r").strip("\n").strip()


def safe_dict_get[T](obj: Mapping[str, Any], value_type: type[T], *keys: str) -> T | None:
    try:
        result = obj

        for key in keys:
            result = result[key]

        return cast(value_type, result)
    except KeyError:
        return None
