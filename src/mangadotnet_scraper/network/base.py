from abc import abstractmethod
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any, Final, override


@dataclass(frozen=True)
class RequestInfo:
    url: str
    method: str
    headers: Mapping[str, str]


class Response(AbstractAsyncContextManager):
    request: Final[RequestInfo]
    status: Final[int]
    headers: Final[Mapping[str, str]]
    reason: Final[str | None]

    @property
    def ok(self) -> bool:
        """Returns ``True`` if ``status`` is less than ``400``, ``False`` if not.

        This is **not** a check for ``200 OK`` but a check that the response
        status is under 400.
        """
        return self.status < 400

    def __init__(
        self,
        request: RequestInfo,
        status: int,
        headers: Mapping[str, str],
        reason: str | None = None,
    ) -> None:
        self.request = request
        self.status = status
        self.headers = headers
        self.reason = reason

    @override
    async def __aexit__(self, *args) -> None:
        await self.close()

    @abstractmethod
    async def read(self) -> bytes: ...

    @abstractmethod
    async def text(self, encoding: str | None = None) -> str: ...

    @abstractmethod
    async def json(self, encoding: str | None = None) -> Any: ...

    def raise_for_status(self) -> None:
        if not self.ok:
            # reason should always be not None for a started response
            assert self.reason is not None

            raise HttpResponseError(
                self.request, self.status, self.reason, self.headers
            )

    @abstractmethod
    async def close(self) -> None: ...


class HttpResponseError(Exception):
    request: Final[RequestInfo]
    status: Final[int]
    message: Final[str]
    headers: Final[Mapping[str, str] | None]

    def __init__(
        self,
        request: RequestInfo,
        status: int,
        message: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.request = request
        self.status = status
        self.message = message
        self.headers = headers


class BaseHttpClientProvider(AbstractAsyncContextManager):
    @override
    async def __aexit__(self, *args) -> None:
        await self.close()

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def get(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> Response: ...

    @abstractmethod
    async def head(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> Response: ...

    @abstractmethod
    async def post(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> Response: ...

    @abstractmethod
    async def put(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> Response: ...

    @abstractmethod
    async def delete(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> Response: ...

    @abstractmethod
    async def options(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> Response: ...

    @abstractmethod
    async def patch(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> Response: ...
