from abc import ABC, abstractmethod
from asyncio import sleep

from aiohttp import (
    AsyncResolver,
    ClientHandlerType,
    ClientRequest,
    ClientResponse,
    ClientSession,
    TCPConnector,
)

from mangadotnet_scraper.camoufox_utils import get_cloudflare_cookies


def create_client(limit=100, **kwargs) -> ClientSession:
    resolver = AsyncResolver(nameservers=["1.1.1.1"])
    connector = TCPConnector(resolver=resolver, limit=limit)
    return ClientSession(connector=connector, middlewares=[CloudflareMiddleware()], **kwargs)


class Middleware(ABC):
    @abstractmethod
    async def __call__(self, request: ClientRequest, handler: ClientHandlerType) -> ClientResponse:
        raise NotImplementedError


class RetryMiddleware(Middleware):
    _max_retry_count: int

    def __init__(self, max_retry_count: int = 5) -> None:
        self._max_retry_count = max_retry_count

    async def __call__(self, request: ClientRequest, handler: ClientHandlerType) -> ClientResponse:
        response: ClientResponse = request.response if isinstance(request.response, ClientResponse) else await handler(request)
        retry_delay: int = 2

        for _ in range(self._max_retry_count):
            if response.ok:
                return response
            else:
                await sleep(retry_delay)
                retry_delay *= 2
                response = await handler(request)

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

            cookie: str | None = self._cookies.get(request.host)

            if cookie is not None:
                request.update_cookies({self._CLOUDFLARE_COOKIE_NAME: cookie})

            return await handler(request)

        response: ClientResponse = request.response if isinstance(request.response, ClientResponse) else await update_and_request()

        if response.headers.get("cf-mitigated") == "challenge":
            data: tuple[str, str] | None = await get_cloudflare_cookies(str(request.url))

            if data is not None:
                self._user_agent = data[0]
                self._cookies.update({request.host: data[1]})

                response = await update_and_request()

        return response
