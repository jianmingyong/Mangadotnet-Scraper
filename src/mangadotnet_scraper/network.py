import logging
from abc import ABC
from asyncio import Lock, sleep
from collections.abc import Callable, Coroutine, Iterable, Mapping
from functools import wraps
from typing import Final

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
    additional_headers: Mapping[str, str] | None = None,
    additional_middlewares: Iterable[ClientMiddlewareType] | None = None,
    **kwargs,
) -> ClientSession:
    if additional_headers is None:
        additional_headers = {}

    if additional_middlewares is None:
        additional_middlewares = []

    headers = {}

    if base_url is not None:
        headers.update({"Origin": base_url})

    if user_agent is not None:
        headers.update({"User-Agent": user_agent})

    headers.update(additional_headers)

    resolver = AsyncResolver(nameservers=["1.1.1.1"])
    connector = TCPConnector(resolver=resolver, ttl_dns_cache=3600)
    return ClientSession(
        base_url,
        connector=connector,
        headers=headers,
        middlewares=[
            RateLimitedMiddleware(),
            *additional_middlewares,
            CloudflareMiddleware(user_agent),
        ],
        **kwargs,
    )


def default_retryable_status(error: ClientResponseError) -> bool:
    if (
        error.headers is not None
        and error.headers.get("cf-mitigated") == "challenge"
    ):
        return True

    return error.status == 408 or error.status == 429 or error.status == 504


def retryable_client_session[**P, R](
    async_func: Callable[P, Coroutine[None, None, R]],
    max_retry: int = 5,
    retry_wait_duration: int = 5,
    retryable_status: Callable[
        [ClientResponseError], bool
    ] = default_retryable_status,
) -> Callable[P, Coroutine[None, None, R]]:

    @wraps(async_func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        for retry in range(max_retry):
            try:
                return await async_func(*args, **kwargs)
            except OSError, ClientConnectionError:
                logging.getLogger(__name__).error(
                    f"Connection lost. Retry attempt {retry + 1}/{max_retry}"
                )
                await sleep(retry_wait_duration * (retry + 1))
            except ClientResponseError as error:
                if retryable_status(error):
                    logging.getLogger(__name__).error(
                        f"Client response with {error.status} ({error.message}). Retry attempt {retry + 1}/{max_retry}"
                    )
                    await sleep(retry_wait_duration * (retry + 1))
                else:
                    raise

        return await async_func(*args, **kwargs)

    return wrapper


class Middleware(ABC):
    async def __call__(
        self, request: ClientRequest, handler: ClientHandlerType
    ) -> ClientResponse:
        return await handler(request)


class RateLimitedMiddleware(Middleware):
    _TOO_MANY_REQUEST_STATUS_CODE = 429
    _RETRY_AFTER_HEADER = "Retry-After"

    _retry_wait_duration: Final[int]
    _lock: Final[Lock]

    def __init__(self, retry_wait_duration: int = 60) -> None:
        self._retry_wait_duration = retry_wait_duration
        self._lock = Lock()

    async def __call__(
        self, request: ClientRequest, handler: ClientHandlerType
    ) -> ClientResponse:
        response = await handler(request)

        if response.status != self._TOO_MANY_REQUEST_STATUS_CODE:
            return response

        async with self._lock:
            response = await handler(request)

            if response.status != self._TOO_MANY_REQUEST_STATUS_CODE:
                return response

            retry_timer = response.headers.get(self._RETRY_AFTER_HEADER)

            if retry_timer is not None and retry_timer.isnumeric():
                retry_timer = int(retry_timer)
            else:
                retry_timer = self._retry_wait_duration

            logging.getLogger(__name__).error(
                f"Request rate limited. Retrying after {retry_timer} seconds..."
            )

            await sleep(retry_timer)

            return await handler(request)


class CloudflareMiddleware(Middleware):
    _CLOUDFLARE_COOKIE_NAME = "cf_clearance"

    _user_agent: str | None
    _cookies: Final[dict[str, str]]
    _lock: Final[Lock]

    def __init__(self, user_agent: str | None = None) -> None:
        self._user_agent = user_agent
        self._cookies = {}
        self._lock = Lock()

    async def __call__(
        self, request: ClientRequest, handler: ClientHandlerType
    ) -> ClientResponse:
        async def update_and_request() -> ClientResponse:
            if self._user_agent is not None:
                request.headers.update({"User-Agent": self._user_agent})

            cookie = self._cookies.get(request.host)

            if cookie is not None:
                request.update_cookies({self._CLOUDFLARE_COOKIE_NAME: cookie})

            return await handler(request)

        response = await update_and_request()

        if response.headers.get("cf-mitigated") != "challenge":
            return response

        async with self._lock:
            response = await update_and_request()

            if response.headers.get("cf-mitigated") != "challenge":
                return response

            logging.getLogger(__name__).error(
                "Request requires cloudflare challenge. Attempting to get cloudflare cookies..."
            )

            data = await get_cloudflare_cookies(
                str(request.url), self._user_agent
            )

            if data is not None:
                self._user_agent = data[0]
                self._cookies.update({request.host: data[1]})

            return await update_and_request()
