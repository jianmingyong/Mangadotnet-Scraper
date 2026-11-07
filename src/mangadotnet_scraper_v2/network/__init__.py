from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from typing import Final

from asynciolimiter import LeakyBucketLimiter, Limiter, StrictLimiter

from mangadotnet_scraper_v2.network.base import BaseHttpClientProvider
from mangadotnet_scraper_v2.network.providers.aiohttp import (
    AioHttpClientProvider,
)


class HttpClient(AbstractAsyncContextManager):
    _provider: Final[BaseHttpClientProvider]
    _limiter: Final[LeakyBucketLimiter | Limiter | StrictLimiter | None]

    def __init__(
        self,
        /,
        base_url: str | None = None,
        user_agent: str | None = None,
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, str] | None = None,
        limiter: LeakyBucketLimiter | Limiter | StrictLimiter | None = None,
    ) -> None:
        self._provider = AioHttpClientProvider(
            base_url, user_agent, headers, cookies
        )
        self._limiter = limiter

    async def __aexit__(self, *args) -> None:
        if self._limiter is not None:
            self._limiter.close()

        await self._provider.close()

    async def get_text(self, url: str, **kwargs) -> str:
        if self._limiter is not None:
            await self._limiter.wait()

        return await self._provider.get_text(url, **kwargs)

    async def get_json(self, url: str, **kwargs) -> str:
        if self._limiter is not None:
            await self._limiter.wait()

        return await self._provider.get_json(url, **kwargs)

    async def get_bytes(self, url: str, **kwargs) -> bytes:
        if self._limiter is not None:
            await self._limiter.wait()

        return await self._provider.get_bytes(url, **kwargs)


__all__ = ["HttpClient"]
