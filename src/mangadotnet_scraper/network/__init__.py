import logging
from asyncio import sleep
from collections.abc import Callable, Coroutine, Mapping
from contextlib import AbstractAsyncContextManager
from functools import wraps
from typing import Any, Final

from asynciolimiter import LeakyBucketLimiter, Limiter, StrictLimiter

from mangadotnet_scraper.network.base import HttpResponseError, Response

from .base import BaseHttpClientProvider
from .providers import AioHttpClientProvider


def default_retryable_status(error: HttpResponseError) -> bool:
    if (
        error.headers is not None
        and error.headers.get("cf-mitigated") == "challenge"
    ):
        return True

    return (
        error.status == 408
        or error.status == 429
        or error.status == 502
        or error.status == 504
        or error.status == 522
    )


def retryable_client_method[**P, R](
    async_func: Callable[P, Coroutine[None, None, R]],
    max_retry: int = 5,
    retry_wait_duration: int = 5,
    retryable_status: Callable[
        [HttpResponseError], bool
    ] = default_retryable_status,
) -> Callable[P, Coroutine[None, None, R]]:

    @wraps(async_func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        for retry in range(max_retry):
            try:
                return await async_func(*args, **kwargs)
            except OSError:
                logging.getLogger(__name__).error(
                    f"Connection lost. Retry attempt {retry + 1}/{max_retry}"
                )
                await sleep(retry_wait_duration * (retry + 1))
            except HttpResponseError as error:
                if retryable_status(error):
                    logging.getLogger(__name__).error(
                        f"Server response with {error.status} ({error.message}). Retry attempt {retry + 1}/{max_retry}"
                    )
                    await sleep(retry_wait_duration * (retry + 1))
                else:
                    raise

        return await async_func(*args, **kwargs)

    return wrapper


class HttpClient(AbstractAsyncContextManager):
    _provider: Final[BaseHttpClientProvider]

    def __init__(
        self,
        base_url: str | None = None,
        user_agent: str | None = None,
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, str] | None = None,
        limiter: LeakyBucketLimiter | Limiter | StrictLimiter | None = None,
    ) -> None:
        self._provider = AioHttpClientProvider(
            base_url, user_agent, headers, cookies, limiter
        )

    async def __aexit__(self, *args) -> None:
        await self._provider.close()

    async def close(self) -> None:
        await self._provider.close()

    async def get(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> Response:
        return await self._provider.get(
            url,
            params,
            cookies,
            headers,
            **kwargs,
        )

    async def head(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> Response:
        return await self._provider.head(
            url,
            params,
            cookies,
            headers,
            **kwargs,
        )

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
        return await self._provider.post(
            url,
            params,
            data,
            json,
            cookies,
            headers,
            **kwargs,
        )

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
        return await self._provider.put(
            url,
            params,
            data,
            json,
            cookies,
            headers,
            **kwargs,
        )

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
        return await self._provider.delete(
            url,
            params,
            data,
            json,
            cookies,
            headers,
            **kwargs,
        )

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
        return await self._provider.options(
            url,
            params,
            data,
            json,
            cookies,
            headers,
            **kwargs,
        )

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
        return await self._provider.patch(
            url,
            params,
            data,
            json,
            cookies,
            headers,
            **kwargs,
        )


__all__ = ["HttpClient"]
