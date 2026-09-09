from abc import ABC, abstractmethod
from asyncio import sleep
from collections.abc import AsyncGenerator, Callable, Coroutine
from functools import wraps
from typing import Final, cast

from aiohttp import (
    AsyncResolver,
    ClientConnectionError,
    ClientHandlerType,
    ClientRequest,
    ClientResponse,
    ClientSession,
    TCPConnector,
)

from mangadotnet_scraper.camoufox_utils import get_cloudflare_cookies


def create_client(base_url: str | None = None, **kwargs) -> ClientSession:
    resolver = AsyncResolver(nameservers=["1.1.1.1"])
    connector = TCPConnector(resolver=resolver)
    return ClientSession(
        base_url, connector=connector, middlewares=[CloudflareMiddleware(), RetryableHandlerMiddleware()], **kwargs
    )


def retryable_client_session[**P, R](
    async_func: Callable[P, Coroutine[None, None, R]], max_retry: int = 5
) -> Callable[P, Coroutine[None, None, R]]:
    @wraps(async_func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        for retry in range(max_retry):
            try:
                return await async_func(*args, **kwargs)
            except ClientConnectionError:
                # Connect failed or disconnect from internet.
                await sleep(2 * (retry + 1))
        return await async_func(*args, **kwargs)

    return wrapper


def retryable_client_session_generator[**P, R](
    async_func: Callable[P, AsyncGenerator[R]], max_retry: int = 5
) -> Callable[P, AsyncGenerator[R]]:
    @wraps(async_func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[R]:
        for retry in range(max_retry):
            try:
                async for item in async_func(*args, **kwargs):
                    yield item
                return
            except ClientConnectionError:
                # Connect failed or disconnect from internet.
                await sleep(2 * (retry + 1))

        async for item in async_func(*args, **kwargs):
            yield item

    return wrapper


class Middleware(ABC):
    @abstractmethod
    async def __call__(self, request: ClientRequest, handler: ClientHandlerType) -> ClientResponse:
        raise NotImplementedError


class RetryableHandlerMiddleware(Middleware):
    _REQUEST_TIMEOUT_STATUS_CODE = 408
    _TOO_MANY_REQUEST_STATUS_CODE = 429
    _GATEWAY_TIMEOUT_STATUS_CODE = 504

    _RETRY_AFTER_HEADER = "Retry-After"

    _max_retry: Final[int]

    def __init__(self, max_retry: int = 5) -> None:
        self._max_retry = max_retry

    async def __call__(self, request: ClientRequest, handler: ClientHandlerType) -> ClientResponse:
        response: ClientResponse = (
            cast(ClientResponse, request.response) if request.response is not None else await handler(request)
        )

        for retry in range(self._max_retry):
            if response.status == self._REQUEST_TIMEOUT_STATUS_CODE:
                # Request timed out. Safe to try this again.
                await sleep(2 * (retry + 1))
                response = await handler(request)
            elif response.status == self._TOO_MANY_REQUEST_STATUS_CODE:
                # Rate limited. Try again after X seconds from _RETRY_AFTER_HEADER.
                retry_timer = response.headers.get(self._RETRY_AFTER_HEADER)
                await sleep(int(retry_timer) if retry_timer is not None else (2 * (retry + 1)))
                response = await handler(request)
            elif response.status == self._GATEWAY_TIMEOUT_STATUS_CODE:
                # Gateway timed out. Safe to try this again.
                await sleep(2 * (retry + 1))
                response = await handler(request)
            else:
                break

        return response


class CloudflareMiddleware(Middleware):
    _CLOUDFLARE_COOKIE_NAME = "cf_clearance"

    _user_agent: str | None
    _cookies: dict[str, str]

    def __init__(self) -> None:
        self._user_agent = None
        self._cookies = {}

    async def __call__(self, request: ClientRequest, handler: ClientHandlerType) -> ClientResponse:
        async def update_and_request() -> ClientResponse:
            if self._user_agent is not None:
                request.headers.update({"User-Agent": self._user_agent})

            cookie = self._cookies.get(request.host)

            if cookie is not None:
                request.update_cookies({self._CLOUDFLARE_COOKIE_NAME: cookie})

            return await handler(request)

        response = (
            cast(ClientResponse, request.response) if request.response is not None else await update_and_request()
        )

        if response.headers.get("cf-mitigated") == "challenge":
            data = await get_cloudflare_cookies(str(request.url))

            if data is not None:
                self._user_agent = data[0]
                self._cookies.update({request.host: data[1]})

                response = await update_and_request()

        return response
