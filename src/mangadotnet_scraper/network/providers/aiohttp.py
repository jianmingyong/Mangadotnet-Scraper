import logging
from abc import ABC
from asyncio import Lock, sleep
from collections.abc import Mapping, MutableMapping
from time import time
from typing import Any, Final, override

from aiohttp import (
    AsyncResolver,
    ClientHandlerType,
    ClientPayloadError,
    ClientRequest,
    ClientResponse,
    ClientSession,
    TCPConnector,
)
from aiohttp.hdrs import (
    RETRY_AFTER,
    USER_AGENT,
    X_RATELIMIT_REMAINING,
    X_RATELIMIT_RESET,
)
from asynciolimiter import LeakyBucketLimiter, Limiter, StrictLimiter
from playwright.async_api import Error
from playwright_captcha import ClickSolver, FrameworkType

from mangadotnet_scraper.camoufox_utils import (
    Browser,
    solve_cloudflare_captcha_interstitial,
)
from mangadotnet_scraper.network.base import (
    HttpClient,
    RequestInfo,
    Response,
)
from mangadotnet_scraper.utilities import is_digit


class AioHttpClientResponse(Response):
    _response: Final[ClientResponse]

    def __init__(self, response: ClientResponse) -> None:
        super().__init__(
            RequestInfo(
                str(response.request_info.url),
                response.request_info.method,
                response.request_info.headers,
            ),
            response.status,
            response.headers,
            response.reason,
        )
        self._response = response

    @override
    async def read(self) -> bytes:
        try:
            return await self._response.read()
        except ClientPayloadError as error:
            raise OSError() from error

    @override
    async def text(self, encoding: str | None = None) -> str:
        try:
            return await self._response.text(encoding)
        except ClientPayloadError as error:
            raise OSError() from error

    @override
    async def json(self, encoding: str | None = None) -> Any:
        try:
            return await self._response.json(
                encoding=encoding, content_type=None
            )
        except ClientPayloadError as error:
            raise OSError() from error

    @override
    async def close(self) -> None:
        self._response.close()


class Middleware(ABC):
    async def __call__(
        self, request: ClientRequest, handler: ClientHandlerType
    ) -> ClientResponse:
        return await handler(request)


class UserRateLimitMiddleware(Middleware):
    _limiter: Final[LeakyBucketLimiter | Limiter | StrictLimiter | None]

    def __init__(
        self,
        limiter: LeakyBucketLimiter | Limiter | StrictLimiter | None = None,
    ):
        self._limiter = limiter

    @override
    async def __call__(
        self, request: ClientRequest, handler: ClientHandlerType
    ) -> ClientResponse:
        if self._limiter is not None:
            await self._limiter.wait()

        return await handler(request)


class ServerRateLimitMiddleware(Middleware):
    _limits: Final[MutableMapping[str, tuple[int, int]]]

    def __init__(self) -> None:
        self._limits = {}

    @override
    async def __call__(
        self, request: ClientRequest, handler: ClientHandlerType
    ) -> ClientResponse:
        limit, reset = self._limits.get(request.url.path, (-1, -1))

        if limit <= 1 and reset > 0:
            logging.getLogger(__name__).info(
                "Request rate limited (%s) Retrying after %s seconds.",
                str(request.request_info.url),
                reset,
            )
            await sleep(reset)

        response = await handler(request)

        remaining = response.headers.get(
            X_RATELIMIT_REMAINING,
            response.headers.get("RateLimit-Remaining"),
        )

        if remaining is not None and is_digit(remaining):
            remaining_limit = int(remaining)
        else:
            remaining_limit = -1

        reset = response.headers.get(
            X_RATELIMIT_RESET, response.headers.get("RateLimit-Reset")
        )

        if reset is not None and is_digit(reset):
            reset_timer = int(reset)
            current_time = int(time())

            if reset_timer > current_time:
                reset_timer -= current_time
        else:
            reset_timer = -1

        self._limits.update({request.url.path: (remaining_limit, reset_timer)})

        return response


class CloudflareMiddleware(Middleware):
    _CLOUDFLARE_COOKIE_NAME = "cf_clearance"

    _browser: Final[Browser]
    _cookies: Final[MutableMapping[str, str]]
    _lock: Final[Lock]

    _user_agent: str | None

    def __init__(self, browser: Browser) -> None:
        self._browser = browser
        self._cookies = {}
        self._lock = Lock()

    async def get_cloudflare_cookies(self, url: str) -> str | None:
        try:
            async with (
                await self._browser.new_context(self._user_agent) as context,
                await context.new_page() as page,
                ClickSolver(
                    framework=FrameworkType.CAMOUFOX, page=page
                ) as solver,
            ):
                response = await page.goto(url)
                assert response is not None

                if not await solve_cloudflare_captcha_interstitial(
                    solver, page, response
                ):
                    logging.getLogger(__name__).error(
                        "Failed to solve cloudflare captcha"
                    )
                    return None

                cookies = await context.cookies(url)
                cookie_value = None

                for cookie in cookies:
                    if cookie.get("name") == "cf_clearance":
                        cookie_value = cookie.get("value")
                        break

                if cookie_value is None:
                    return None

            logging.getLogger(__name__).info(
                "Cloudflare cookies obtained for user agent (%s): %s",
                self._user_agent,
                cookie_value,
            )

            return cookie_value
        except Error:
            logging.getLogger(__name__).exception(
                "Failed to get cloudflare cookies due to camoufox error"
            )
            return None

    @override
    async def __call__(
        self, request: ClientRequest, handler: ClientHandlerType
    ) -> ClientResponse:
        self._user_agent = request.headers.get(USER_AGENT)
        assert self._user_agent is not None

        async def update_and_request() -> ClientResponse:
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

            logging.getLogger(__name__).info(
                "Response returned cloudflare challenge. Attempting to get cloudflare cookies."
            )

            data = await self.get_cloudflare_cookies(str(request.url))

            if data is not None:
                self._cookies.update({request.host: data})

            return await update_and_request()


class RateLimitedMiddleware(Middleware):
    _TOO_MANY_REQUEST_STATUS_CODE = 429

    _retry_wait_duration: Final[int]
    _lock: Final[Lock]

    def __init__(self, retry_wait_duration: int = 60) -> None:
        self._retry_wait_duration = retry_wait_duration
        self._lock = Lock()

    @override
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

            retry_timer = response.headers.get(
                RETRY_AFTER,
                response.headers.get(
                    X_RATELIMIT_RESET,
                    response.headers.get("RateLimit-Reset"),
                ),
            )

            if retry_timer is not None and is_digit(retry_timer):
                retry_timer = int(retry_timer)
            else:
                retry_timer = self._retry_wait_duration

            current_time = int(time())

            if retry_timer > current_time:
                retry_timer -= current_time

            logging.getLogger(__name__).info(
                "Request rate limited (%s) Retrying after %s seconds.",
                str(request.request_info.url),
                retry_timer,
            )

            await sleep(retry_timer)

            return await handler(request)


class AioHttpClient(HttpClient):
    _client: Final[ClientSession]

    def __init__(
        self,
        browser: Browser,
        base_url: str | None = None,
        user_agent: str | None = None,
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, str] | None = None,
        limiter: LeakyBucketLimiter | Limiter | StrictLimiter | None = None,
        **kwargs,
    ) -> None:
        resolver = AsyncResolver(nameservers=["1.1.1.1"])
        connector = TCPConnector(resolver=resolver, ttl_dns_cache=300)

        _headers = {}

        if headers is not None:
            _headers.update(headers)

        if user_agent is not None:
            _headers.update({USER_AGENT: user_agent})

        middlewares = [
            UserRateLimitMiddleware(limiter),
            ServerRateLimitMiddleware(),
            RateLimitedMiddleware(),
            CloudflareMiddleware(browser),
        ]

        if kwargs.get("middlewares") is not None:
            middlewares = kwargs.get("middlewares")
            del kwargs["middlewares"]

        self._client = ClientSession(
            base_url=base_url,
            connector=connector,
            cookies=cookies,
            headers=_headers,
            middlewares=middlewares,
            **kwargs,
        )

    @override
    async def close(self) -> None:
        await self._client.close()

    @override
    async def get(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> Response:
        return AioHttpClientResponse(
            await self._client.get(
                url,
                params=params,
                cookies=cookies,
                headers=headers,
                **kwargs,
            )
        )

    @override
    async def head(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> Response:
        return AioHttpClientResponse(
            await self._client.head(
                url,
                params=params,
                cookies=cookies,
                headers=headers,
                **kwargs,
            )
        )

    @override
    async def post(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> Response:
        return AioHttpClientResponse(
            await self._client.post(
                url,
                params=params,
                data=data,
                json=json,
                cookies=cookies,
                headers=headers,
                **kwargs,
            )
        )

    @override
    async def put(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> Response:
        return AioHttpClientResponse(
            await self._client.put(
                url,
                params=params,
                data=data,
                json=json,
                cookies=cookies,
                headers=headers,
                **kwargs,
            )
        )

    @override
    async def delete(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> Response:
        return AioHttpClientResponse(
            await self._client.delete(
                url,
                params=params,
                data=data,
                json=json,
                cookies=cookies,
                headers=headers,
                **kwargs,
            )
        )

    @override
    async def options(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> Response:
        return AioHttpClientResponse(
            await self._client.options(
                url,
                params=params,
                data=data,
                json=json,
                cookies=cookies,
                headers=headers,
                **kwargs,
            )
        )

    @override
    async def patch(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> Response:
        return AioHttpClientResponse(
            await self._client.patch(
                url,
                params=params,
                data=data,
                json=json,
                cookies=cookies,
                headers=headers,
                **kwargs,
            )
        )
