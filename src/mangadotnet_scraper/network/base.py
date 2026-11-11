from abc import abstractmethod
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any, Final


class HttpResponseError(Exception):
    status: Final[int]
    message: Final[str]
    headers: Final[Mapping[str, str] | None]

    def __init__(
        self,
        status: int,
        message: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.status = status
        self.message = message
        self.headers = headers


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
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        raise_for_status: bool = True,
        **kwargs,
    ) -> str: ...

    @abstractmethod
    async def get_json(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        raise_for_status: bool = True,
        **kwargs,
    ) -> Any: ...

    @abstractmethod
    async def get_bytes(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        raise_for_status: bool = True,
        **kwargs,
    ) -> bytes: ...

    @abstractmethod
    async def head(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        raise_for_status: bool = True,
        **kwargs,
    ) -> Mapping[str, str]: ...

    @abstractmethod
    async def post_text(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        raise_for_status: bool = True,
        **kwargs,
    ) -> str: ...

    @abstractmethod
    async def post_json(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        raise_for_status: bool = True,
        **kwargs,
    ) -> Any: ...

    @abstractmethod
    async def post_bytes(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        raise_for_status: bool = True,
        **kwargs,
    ) -> bytes: ...
