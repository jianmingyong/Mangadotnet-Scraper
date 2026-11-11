from collections.abc import Mapping
from re import split as re_split
from typing import Any

from yarl import URL


def clean_string(value: str) -> str:
    return "".join(c if c.isprintable() else " " for c in value).strip()


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


def clean_chapter_title(chapter: float, title: str | None = None) -> str:
    if title is None or title == "" or title == str(chapter):
        return f"Chapter {chapter:.1f}".rstrip("0").rstrip(".")
    else:
        return title


def normalize_url(url: str | URL, base_url: str | URL) -> str:
    url = URL(url)
    base_url = URL(base_url)

    if url.is_absolute():
        return str(url)
    else:
        return str(base_url.join(url))


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
