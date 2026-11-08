import json
import logging
from collections.abc import (
    Mapping,
    MutableMapping,
    MutableSequence,
    Sequence,
)
from typing import Any, Final


class MangaDotNetScraperConfig:
    _config_file: Final[str]
    _data: dict[str, Any]

    @property
    def data_file(self) -> str:
        return self._get_config("data_file", str, "data.db")

    @property
    def mangadotnet_username(self) -> str | None:
        return self._get_config("mangadotnet_username", str)

    @property
    def mangadotnet_password(self) -> str | None:
        return self._get_config("mangadotnet_password", str)

    @property
    def mangadotnet_otp(self) -> str | None:
        return self._get_config("mangadotnet_otp", str)

    @property
    def mangadotnet_user_session(self) -> str | None:
        return self._get_config("mangadotnet_user_session", str)

    @mangadotnet_user_session.setter
    def mangadotnet_user_session(self, value: str | None) -> None:
        self.set_config("mangadotnet_user_session", value)

    @property
    def fetch_concurrency(self) -> int:
        return self._get_config("fetch_concurrency", int, 12)

    @property
    def download_concurrency(self) -> int:
        return self._get_config("download_concurrency", int, 12)

    @property
    def download_max_retry(self) -> int:
        return self._get_config("download_max_retry", int, 5)

    @property
    def upload_concurrency(self) -> int:
        return self._get_config("upload_concurrency", int, 10)

    @property
    def upload_chunk_size(self) -> int:
        return self._get_config("upload_chunk_size", int, 4 * 1024 * 1024)

    @property
    def upload_verify_duration(self) -> int:
        return self._get_config("upload_verify_duration", int, 60)

    @property
    def enabled_sources(self) -> Sequence[str]:
        return self._get_config("enabled_sources", Sequence, [])

    @enabled_sources.setter
    def enabled_sources(self, value: Sequence[str]) -> None:
        self.set_config("enabled_sources", value)

    def __init__(self, file: str | None = None):
        self._config_file = file if file is not None else "config.json"

    def load(self) -> None:
        try:
            with open(self._config_file, "rt") as file:
                self._data = json.load(file)
        except OSError:
            logging.getLogger(__name__).exception(
                "Config file cannot be read due to an error."
            )
            self._data = {}

    def save(self) -> None:
        try:
            with open(self._config_file, "wt") as file:
                json.dump(self._data, file, indent=4)
        except OSError:
            logging.getLogger(__name__).exception(
                "Config file cannot be written due to an error."
            )

    def get_source_config(self, source_id: str) -> Mapping[str, Any]:
        return self._get_config(f"sources:{source_id}", Mapping[str, Any], {})

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

    def _get_config[T](
        self, key: str, expect_type: type[T], default: T = None
    ) -> T:
        value = self.get_config(key, default)

        if isinstance(value, expect_type):
            return value
        else:
            return default
