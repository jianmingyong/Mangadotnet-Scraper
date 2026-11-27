import logging
from asyncio import sleep
from collections.abc import Callable, Coroutine, Mapping
from functools import wraps

from asynciolimiter import LeakyBucketLimiter, Limiter, StrictLimiter

from mangadotnet_scraper.camoufox_utils import Browser

from .base import HttpClient, HttpResponseError, Response
from .providers import AioHttpClient

__all__ = [
    "HttpClient",
    "HttpResponseError",
    "Response",
    "create_http_client",
    "retryable_client_method",
]


def _default_retryable_status(error: HttpResponseError) -> bool:
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
    ] = _default_retryable_status,
) -> Callable[P, Coroutine[None, None, R]]:
    @wraps(async_func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        for retry in range(max_retry):
            try:
                return await async_func(*args, **kwargs)
            except OSError:
                logging.getLogger(__name__).exception(
                    f"Connection lost. Retry attempt {retry + 1}/{max_retry}"
                )
                await sleep(retry_wait_duration * (retry + 1))
            except HttpResponseError as error:
                if retryable_status(error):
                    logging.getLogger(__name__).warning(
                        f"Server response with {error.status} ({error.message}). Retry attempt {retry + 1}/{max_retry}"
                    )
                    await sleep(retry_wait_duration * (retry + 1))
                else:
                    raise

        return await async_func(*args, **kwargs)

    return wrapper


def create_http_client(
    browser: Browser,
    base_url: str | None = None,
    user_agent: str | None = None,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
    limiter: LeakyBucketLimiter | Limiter | StrictLimiter | None = None,
    **kwargs,
) -> HttpClient:
    return AioHttpClient(
        browser, base_url, user_agent, headers, cookies, limiter, **kwargs
    )
