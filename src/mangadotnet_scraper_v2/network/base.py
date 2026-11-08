from abc import abstractmethod
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any, Final


class HttpResponseError(Exception):
    status: Final[int]
    message: Final[str]

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message


class BaseHttpClientProvider(AbstractAsyncContextManager):
    async def __aexit__(self, *args) -> None:
        await self.close()

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def get_text(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> str: ...

    @abstractmethod
    async def get_json(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> str: ...

    @abstractmethod
    async def get_bytes(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> bytes: ...
