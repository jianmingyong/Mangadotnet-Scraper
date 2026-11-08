import json
import logging
from collections.abc import Mapping, MutableMapping, MutableSequence, Sequence
from typing import Any, Final, override

from mangadotnet_scraper_v2.config.base import ConfigProvider


class JsonConfigProvider(ConfigProvider):
    _config_file: Final[str]
    _data: dict[str, Any]

    def __init__(self, file: str | None = None):
        self._config_file = file if file is not None else "config.json"

    @override
    def load(self) -> None:
        try:
            with open(self._config_file, "rt") as file:
                self._data = json.load(file)
        except OSError:
            logging.getLogger(__name__).exception(
                "Config file not found or not readable. Using default config."
            )
            self._data = {}

    @override
    def save(self) -> None:
        try:
            with open(self._config_file, "wt") as file:
                json.dump(self._data, file, indent=4)
        except OSError:
            logging.getLogger(__name__).exception(
                "Unable to write config file."
            )

    @override
    def get_config(self, key: str, default: Any = None) -> Any:
        value = self._data

        for k in key.split(":"):
            if k.isnumeric():
                if not isinstance(value, Sequence):
                    return default

                try:
                    value = value[int(k)]
                except IndexError:
                    return default
            else:
                if not isinstance(value, Mapping):
                    return default

                value = value.get(k, default)

        return value

    @override
    def set_config(self, key: str, value: Any) -> None:
        section = self._data

        keys = key.split(":")
        keys_length = len(keys)

        for i in range(keys_length):
            k = keys[i]

            if k.isnumeric():
                k = int(k)

                if not isinstance(section, MutableSequence):
                    raise KeyError("Invalid key")

                if k >= len(section):
                    raise IndexError("Invalid key")

                if i == keys_length - 1:
                    section[k] = value
                else:
                    if keys[i + 1].isnumeric() and not isinstance(
                        section[k], MutableSequence
                    ):
                        section[k] = []
                    elif not isinstance(section[k], MutableMapping):
                        section[k] = {}

                    section = section[k]
            else:
                if not isinstance(section, MutableMapping):
                    raise KeyError("Invalid key")

                if i == keys_length - 1:
                    section[k] = value
                else:
                    if keys[i + 1].isnumeric() and not isinstance(
                        section[k], MutableSequence
                    ):
                        section[k] = []
                    elif not isinstance(section[k], MutableMapping):
                        section[k] = {}

                    section = section[k]
