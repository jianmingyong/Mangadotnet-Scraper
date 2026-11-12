from collections.abc import Mapping, Sequence
from typing import Any, Final

from .base import ConfigProvider


class Config:
    _provider: Final[ConfigProvider]

    @property
    def mangadotnet_username(self) -> str | None:
        return self._get_config("mangadotnet_username", str | None)

    @property
    def mangadotnet_password(self) -> str | None:
        return self._get_config("mangadotnet_password", str | None)

    @property
    def mangadotnet_otp(self) -> str | None:
        return self._get_config("mangadotnet_otp", str | None)

    @property
    def mangadotnet_user_session(self) -> str | None:
        return self._get_config("mangadotnet_user_session", str | None)

    @mangadotnet_user_session.setter
    def mangadotnet_user_session(self, value: str | None) -> None:
        self._set_config("mangadotnet_user_session", value)

    @property
    def fetch_concurrency(self) -> int:
        return self._get_config("fetch_concurrency", int, 12)

    @fetch_concurrency.setter
    def fetch_concurrency(self, value: int) -> None:
        self._set_config("fetch_concurrency", value)

    @property
    def download_concurrency(self) -> int:
        return self._get_config("download_concurrency", int, 12)

    @download_concurrency.setter
    def download_concurrency(self, value: int) -> None:
        return self._set_config("download_concurrency", value)

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
        self._set_config("enabled_sources", value)

    def __init__(self, provider: ConfigProvider) -> None:
        self._provider = provider

    def load(self) -> None:
        self._provider.load()

    def save(self) -> None:
        self._provider.save()

    def get_source_config(self, source_id: str) -> Mapping[str, Any]:
        return self._get_config(f"sources:{source_id}", Mapping, {})

    def _get_config[T](
        self, key: str, expect_type: type[T], default: T = None
    ) -> T:
        value = self._provider.get_config(key, default)

        if isinstance(value, expect_type):
            return value
        else:
            return default

    def _set_config(self, key: str, value: Any) -> None:
        self._provider.set_config(key, value)


__all__ = ["Config", "ConfigProvider"]
