import json
from typing import Final, TypedDict


class MangaDotNetScraperConfig:
    class Data(TypedDict):
        mangadotnet_username: str | None
        mangadotnet_password: str | None
        mangadotnet_user_session: str | None

        fetch_concurrency: int | None

        download_concurrency: int | None

        upload_concurrency: int | None
        upload_verify_duration: int | None

    _CONFIG_FILE_PATH: Final[str] = "./config.json"

    _DEFAULT_CONFIG: Final[Data] = {
        "mangadotnet_username": "",
        "mangadotnet_password": "",
        "mangadotnet_user_session": None,

        "fetch_concurrency": 12,

        "download_concurrency": 12,

        "upload_concurrency": 10,
        "upload_verify_duration": 120,
    }

    def __init__(self):
        self._data: MangaDotNetScraperConfig.Data = self._DEFAULT_CONFIG

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
    def mangadotnet_user_session(self, value: str) -> None:
        self._data["mangadotnet_user_session"] = value

    @property
    def fetch_concurrency(self) -> int:
        value: int | None = self._data.get("fetch_concurrency")
        return value if value is not None else 12

    @property
    def download_concurrency(self) -> int:
        value: int | None = self._data.get("download_concurrency")
        return value if value is not None else 12

    @property
    def upload_concurrency(self) -> int:
        value: int | None = self._data.get("upload_concurrency")
        return value if value is not None else 10

    @property
    def upload_verify_duration(self) -> int:
        value: int | None = self._data.get("upload_verify_duration")
        return value if value is not None else 120

    def load_config(self):
        try:
            with open(self._CONFIG_FILE_PATH, "rt+") as f:
                self._data = json.load(f)
        except FileNotFoundError:
            self._data = self._DEFAULT_CONFIG

    def save_config(self):
        with open(self._CONFIG_FILE_PATH, "wt+") as f:
            json.dump(self._data, f, indent=4)
