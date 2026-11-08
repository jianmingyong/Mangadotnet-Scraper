import logging
from abc import ABC
from asyncio import Lock, sleep
from collections.abc import Mapping
from typing import Any, Final

from aiohttp import (
    AsyncResolver,
    ClientHandlerType,
    ClientRequest,
    ClientResponse,
    ClientResponseError,
    ClientSession,
    TCPConnector,
)

from mangadotnet_scraper_v2.camoufox_utils import get_cloudflare_cookies
from mangadotnet_scraper_v2.network.base import (
    BaseHttpClientProvider,
    HttpResponseError,
)


class Middleware(ABC):
    async def __call__(
        self, request: ClientRequest, handler: ClientHandlerType
    ) -> ClientResponse:
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


class AioHttpClientProvider(BaseHttpClientProvider):
    _client: Final[ClientSession]

    def __init__(
        self,
        base_url: str | None = None,
        user_agent: str | None = None,
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, str] | None = None,
    ) -> None:
        resolver = AsyncResolver(nameservers=["1.1.1.1"])
        connector = TCPConnector(resolver=resolver, ttl_dns_cache=300)

        _headers = {}

        if headers is not None:
            _headers.update(headers)

        if user_agent is not None:
            _headers.update({"User-Agent": user_agent})

        self._client = ClientSession(
            base_url=base_url,
            connector=connector,
            cookies=cookies,
            headers=_headers,
            middlewares=[
                RateLimitedMiddleware(),
                CloudflareMiddleware(user_agent),
            ],
        )

    async def close(self) -> None:
        await self._client.close()

    async def get_text(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> str:
        try:
            async with self._client.get(
                url,
                params=params,
                data=data,
                json=json,
                cookies=cookies,
                headers=headers,
                **kwargs,
            ) as response:
                response.raise_for_status()
                return await response.text(encoding="utf-8")
        except ClientResponseError as error:
            raise HttpResponseError(error.status, error.message) from error

    async def get_json(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> str:
        try:
            async with self._client.get(
                url,
                params=params,
                data=data,
                json=json,
                cookies=cookies,
                headers=headers,
                **kwargs,
            ) as response:
                response.raise_for_status()
                return await response.json(
                    encoding="utf-8",
                    content_type=response.content_type,
                )
        except ClientResponseError as error:
            raise HttpResponseError(error.status, error.message) from error

    async def get_bytes(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> bytes:
        try:
            async with self._client.get(
                url,
                params=params,
                data=data,
                json=json,
                cookies=cookies,
                headers=headers,
                **kwargs,
            ) as response:
                response.raise_for_status()
                return await response.read()
        except ClientResponseError as error:
            raise HttpResponseError(error.status, error.message) from error
