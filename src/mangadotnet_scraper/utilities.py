from collections.abc import Mapping
from re import split as re_split
from typing import Any


def clean_string(value: str) -> str:
    return value.replace("\u200f", "").strip("\r").strip("\n").strip()


def clean_alt_titles(alt_title: str | None) -> list[str]:
    if alt_title is None:
        return []
    else:
        result = []

        for x in re_split(r"[/\\\r\n]+", alt_title):
            x = clean_string(x)
            if len(x) > 0:
                result.append(x)

        return result


def normalize_url(url: str, base_url: str) -> str:
    if url.startswith("/"):
        return f"{base_url.rstrip('/')}{url}"
    else:
        return url


def dict_get_recursive(
    obj: Mapping[str, Any], *keys: str, default: Any = None
) -> Any:
    if not isinstance(obj, Mapping):
        return default

    try:
        result = obj

        for key in keys:
            result = result[key]

        return result
    except KeyError:
        return default
