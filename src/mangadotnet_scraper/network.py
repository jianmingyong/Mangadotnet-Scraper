from abc import ABC
from asyncio import Lock, sleep
from collections.abc import Callable, Coroutine, Iterable, Mapping
from functools import wraps
from typing import Final

from aiodns.error import DNSError
from aiohttp import (
    AsyncResolver,
    ClientConnectionError,
    ClientHandlerType,
    ClientMiddlewareType,
    ClientRequest,
    ClientResponse,
    ClientResponseError,
    ClientSession,
    TCPConnector,
)

from mangadotnet_scraper.camoufox_utils import get_cloudflare_cookies


def create_client(
    base_url: str | None = None,
    user_agent: str | None = None,
    additional_headers: Mapping[str, str] = {},
    additional_middlewares: Iterable[ClientMiddlewareType] = [],
    **kwargs,
) -> ClientSession:
    headers = {}
    headers.update(additional_headers)

    if base_url is not None:
        headers.update({"Origin": base_url})

    if user_agent is not None:
        headers.update({"User-Agent": user_agent})

    resolver = AsyncResolver(nameservers=["1.1.1.1"])
    connector = TCPConnector(resolver=resolver, ttl_dns_cache=3600)
    return ClientSession(
        base_url,
        connector=connector,
        headers=headers,
        middlewares=[
            RetryableHandlerMiddleware(),
            *additional_middlewares,
            CloudflareMiddleware(user_agent),
        ],
        **kwargs,
    )


def default_retryable_status(error: ClientResponseError) -> bool:
    if error.headers is not None and error.headers.get("cf-mitigated") == "challenge":
        return True

    return error.status == 408 or error.status == 504


def retryable_client_session[**P, R](
    async_func: Callable[P, Coroutine[None, None, R]],
    max_retry: int = 5,
    retry_wait: int = 2,
    retryable_status: Callable[[ClientResponseError], bool] = default_retryable_status,
) -> Callable[P, Coroutine[None, None, R]]:

    @wraps(async_func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        for retry in range(max_retry):
            try:
                return await async_func(*args, **kwargs)
            except DNSError:
                # DNS Resolve error
                await sleep(retry_wait * (retry + 1))
            except ClientConnectionError:
                # Connect failed or disconnect from internet.
                await sleep(retry_wait * (retry + 1))
            except ClientResponseError as error:
                # Client received non ok status.
                if retryable_status(error):
                    await sleep(retry_wait * (retry + 1))
                else:
                    raise

        return await async_func(*args, **kwargs)

    return wrapper


class Middleware(ABC):
    async def __call__(self, request: ClientRequest, handler: ClientHandlerType) -> ClientResponse:
        return await handler(request)


class RetryableHandlerMiddleware(Middleware):
    _TOO_MANY_REQUEST_STATUS_CODE = 429
    _RETRY_AFTER_HEADER = "Retry-After"

    _lock: Final[Lock]
    _retry_wait_duration: Final[int]

    def __init__(self, retry_wait_duration: int = 60) -> None:
        self._lock = Lock()
        self._retry_wait_duration = retry_wait_duration

    async def __call__(self, request: ClientRequest, handler: ClientHandlerType) -> ClientResponse:
        response = await handler(request)

        if response.status == self._TOO_MANY_REQUEST_STATUS_CODE:
            # Rate limited. Try again after X seconds from _RETRY_AFTER_HEADER.
            async with self._lock:
                response = await handler(request)

                if response.status == self._TOO_MANY_REQUEST_STATUS_CODE:
                    retry_timer = response.headers.get(self._RETRY_AFTER_HEADER)

                    if retry_timer is None or (retry_timer is not None and not retry_timer.isnumeric()):
                        retry_timer = self._retry_wait_duration
                    else:
                        retry_timer = int(retry_timer)

                    await sleep(retry_timer)

                    return await handler(request)

        return response


class CloudflareMiddleware(Middleware):
    _CLOUDFLARE_COOKIE_NAME = "cf_clearance"

    _user_agent: str | None
    _cookies: Final[dict[str, str]]
    _lock: Final[Lock]

    def __init__(self, user_agent: str | None = None) -> None:
        self._user_agent = user_agent
        self._cookies = {}
        self._lock = Lock()

    async def __call__(self, request: ClientRequest, handler: ClientHandlerType) -> ClientResponse:
        async def update_and_request() -> ClientResponse:
            if self._user_agent is not None:
                request.headers.update({"User-Agent": self._user_agent})

            cookie = self._cookies.get(request.host)

            if cookie is not None:
                request.update_cookies({self._CLOUDFLARE_COOKIE_NAME: cookie})

            return await handler(request)

        response = await update_and_request()

        if response.headers.get("cf-mitigated") == "challenge":
            async with self._lock:
                response = await update_and_request()

                if response.headers.get("cf-mitigated") == "challenge":
                    data = await get_cloudflare_cookies(str(request.url), self._user_agent)

                    if data is not None:
                        self._user_agent = data[0]
                        self._cookies.update({request.host: data[1]})
                        return await update_and_request()

        return response
