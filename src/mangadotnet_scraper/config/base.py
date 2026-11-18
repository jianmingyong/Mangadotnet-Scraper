from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any


class ConfigProvider(ABC):
    @property
    def mangadotnet_username(self) -> str | None:
        return self.get_config("mangadotnet_username")

    @property
    def mangadotnet_password(self) -> str | None:
        return self.get_config("mangadotnet_password")

    @property
    def mangadotnet_otp(self) -> str | None:
        return self.get_config("mangadotnet_otp")

    @property
    def mangadotnet_user_session(self) -> str | None:
        return self.get_config("mangadotnet_user_session", str | None)

    @mangadotnet_user_session.setter
    def mangadotnet_user_session(self, value: str | None) -> None:
        self.set_config("mangadotnet_user_session", value)

    @property
    def fetch_concurrency(self) -> int:
        return self.get_config("fetch_concurrency", 12)

    @fetch_concurrency.setter
    def fetch_concurrency(self, value: int) -> None:
        self.set_config("fetch_concurrency", value)

    @property
    def download_concurrency(self) -> int:
        return self.get_config("download_concurrency", 12)

    @download_concurrency.setter
    def download_concurrency(self, value: int) -> None:
        return self.set_config("download_concurrency", value)

    @property
    def download_max_retry(self) -> int:
        return self.get_config("download_max_retry", 5)

    @property
    def upload_concurrency(self) -> int:
        return self.get_config("upload_concurrency", 10)

    @property
    def upload_chunk_size(self) -> int:
        return self.get_config("upload_chunk_size", 4 * 1024 * 1024)

    @property
    def upload_verify_duration(self) -> int:
        return self.get_config("upload_verify_duration", 60)

    @property
    def enabled_sources(self) -> Sequence[str]:
        return self.get_config("enabled_sources", [])

    @enabled_sources.setter
    def enabled_sources(self, value: Sequence[str]) -> None:
        self.set_config("enabled_sources", value)

    @abstractmethod
    def load(self) -> None: ...

    @abstractmethod
    def save(self) -> None: ...

    @abstractmethod
    def get_config(self, key: str, default: Any = None) -> Any: ...

    @abstractmethod
    def set_config(self, key: str, value: Any) -> None: ...

    def get_source_config(self, source_id: str) -> Mapping[str, Any]:
        return self.get_config(f"sources:{source_id}", {})
