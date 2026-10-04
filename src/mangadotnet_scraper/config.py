import json
from collections.abc import Iterable
from typing import Final, NotRequired, TypedDict


class MangaDotNetScraperConfig:
    class Data(TypedDict):
        data_file: NotRequired[str]

        mangadotnet_username: NotRequired[str]
        mangadotnet_password: NotRequired[str]
        mangadotnet_user_session: NotRequired[str | None]

        fetch_concurrency: NotRequired[int]

        download_concurrency: NotRequired[int]
        download_max_retry: NotRequired[int]

        upload_concurrency: NotRequired[int]
        upload_chunk_size: NotRequired[int]
        upload_verify_duration: NotRequired[int]

        enabled_modules: NotRequired[Iterable[str]]

    _CONFIG_FILE_PATH: Final[str] = "./config.json"

    _DEFAULT_CONFIG: Final[Data] = {
        "data_file": "data.db",
        "mangadotnet_username": "",
        "mangadotnet_password": "",
        "mangadotnet_user_session": None,
        "fetch_concurrency": 12,
        "download_concurrency": 12,
        "download_max_retry": 5,
        "upload_concurrency": 10,
        "upload_chunk_size": 4 * 1024 * 1024,
        "upload_verify_duration": 60,
        "enabled_modules": set(),
    }

    def __init__(self) -> None:
        self._data: self.Data = self._DEFAULT_CONFIG

    def _return_or_default[T](self, value: T | None, default: T) -> T:
        return value if value is not None else default

    @property
    def data_file(self) -> str:
        return self._return_or_default(self._data.get("data_file"), "data.db")

    @property
    def mangadotnet_username(self) -> str | None:
        return self._data.get("mangadotnet_username")

    @property
    def mangadotnet_password(self) -> str | None:
        return self._data.get("mangadotnet_password")

    @property
    def mangadotnet_user_session(self) -> str | None:
        return self._data.get("mangadotnet_user_session")

    @mangadotnet_user_session.setter
    def mangadotnet_user_session(self, value: str | None) -> None:
        self._data["mangadotnet_user_session"] = value

    @property
    def fetch_concurrency(self) -> int:
        return self._return_or_default(self._data.get("fetch_concurrency"), 12)

    @property
    def download_concurrency(self) -> int:
        return self._return_or_default(
            self._data.get("download_concurrency"), 12
        )

    @property
    def download_max_retry(self) -> int:
        return self._return_or_default(self._data.get("download_max_retry"), 5)

    @property
    def upload_concurrency(self) -> int:
        return self._return_or_default(
            self._data.get("upload_concurrency"), 10
        )

    @property
    def upload_chunk_size(self) -> int:
        return self._return_or_default(
            self._data.get("upload_chunk_size"), 4 * 1024 * 1024
        )

    @property
    def upload_verify_duration(self) -> int:
        return self._return_or_default(
            self._data.get("upload_verify_duration"), 60
        )

    @property
    def enabled_modules(self) -> Iterable[str]:
        return self._return_or_default(self._data.get("enabled_modules"), [])

    @enabled_modules.setter
    def enabled_modules(self, value: Iterable[str]) -> None:
        self._data["enabled_modules"] = value

    def load_config(self) -> None:
        try:
            with open(self._CONFIG_FILE_PATH, "rt+") as f:
                self._data = json.load(f)
        except FileNotFoundError:
            self._data = self._DEFAULT_CONFIG

    def save_config(self) -> None:
        with open(self._CONFIG_FILE_PATH, "wt+") as f:
            json.dump(self._data, f, indent=4)
