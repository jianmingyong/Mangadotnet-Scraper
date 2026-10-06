import mimetypes
from abc import abstractmethod
from collections.abc import AsyncIterable, Iterable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from types import TracebackType
from typing import (
    Any,
    Final,
    Literal,
    NotRequired,
    Required,
    Self,
    TypedDict,
    Unpack,
)

from aiohttp import ClientMiddlewareType, ClientSession
from aiohttp.client import _RequestOptions
from aiohttp.typedefs import StrOrURL

from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.error import FetchError, SeriesNotFoundError
from mangadotnet_scraper.network import create_client, retryable_client_session


@dataclass(frozen=True)
class MangaListing:
    manga_id: str
    title: str
    link: str


@dataclass(frozen=True)
class MangaDetail:
    title: str
    alt_titles: Sequence[str]
    chapters: Sequence[MangaChapter]


@dataclass(frozen=True)
class MangaChapter:
    language: str
    group: str
    type: Literal["chapter", "volume"]
    chapter_number: float | None
    volume_number: float | None
    title: str
    link: str
    chapter_id: str


@dataclass(frozen=True)
class MangaPage:
    page_number: int
    image_link: str
    data: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class MangaImage:
    filename: str
    data: bytes


class BaseModuleArgs(TypedDict):
    module_id: Required[str]
    display_name: Required[str]
    language: NotRequired[str]
    version: NotRequired[int]

    base_url: Required[str]
    base_api_url: NotRequired[str]

    user_agent: NotRequired[str]
    additional_headers: NotRequired[Mapping[str, str]]
    additional_middlewares: NotRequired[Iterable[ClientMiddlewareType]]


class BaseModule(AbstractAsyncContextManager):
    config: Final[MangaDotNetScraperConfig]

    module_id: Final[str]
    display_name: Final[str]
    language: Final[str]
    version: Final[int]

    base_url: Final[str]
    base_api_url: Final[str]

    user_agent: Final[str | None]
    additional_headers: Final[Mapping[str, str]]
    additional_middlewares: Final[Iterable[ClientMiddlewareType]]

    fetch_concurrency: int
    download_concurrency: int
    upload_concurrency: int

    session: ClientSession

    def __init__(
        self,
        config: MangaDotNetScraperConfig,
        **kwargs: Unpack[BaseModuleArgs],
    ) -> None:
        self.config = config

        self.module_id = kwargs["module_id"]
        self.display_name = kwargs["display_name"]
        self.language = kwargs.get("language", "en")
        self.version = kwargs.get("version", 1)

        self.base_url = kwargs["base_url"]
        self.base_api_url = kwargs.get("base_api_url", self.base_url)

        self.user_agent = kwargs.get("user_agent", None)
        self.additional_headers = kwargs.get("additional_headers", {})
        self.additional_middlewares = kwargs.get("additional_middlewares", [])

        self.fetch_concurrency = config.fetch_concurrency
        self.download_concurrency = config.download_concurrency
        self.upload_concurrency = config.upload_concurrency

    @classmethod
    def create_module(cls, config: MangaDotNetScraperConfig) -> Self:
        if cls is BaseModule:
            raise ValueError(
                "Cannot initialize base module. Please use the constructor instead."
            )

        # pyrefly: ignore [missing-argument]
        return cls(config)

    async def __aenter__(self) -> Self:
        await self.initialize()
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def initialize(self) -> None:
        self.session = create_client(
            base_url=self.base_api_url,
            user_agent=self.user_agent,
            additional_headers=self.additional_headers,
            additional_middlewares=self.additional_middlewares,
        )

    async def close(self) -> None:
        await self.session.close()

    @retryable_client_session
    async def get_html(
        self,
        url: StrOrURL,
        **kwargs: Unpack[_RequestOptions],
    ) -> str:
        async with self.session.get(url, **kwargs) as response:
            response.raise_for_status()
            return await response.text("utf-8")

    @retryable_client_session
    async def get_json(
        self,
        url: StrOrURL,
        **kwargs: Unpack[_RequestOptions],
    ) -> Any:
        async with self.session.get(url, **kwargs) as response:
            response.raise_for_status()
            return await response.json(encoding="utf-8")

    @retryable_client_session
    async def post_json(
        self,
        url: StrOrURL,
        **kwargs: Unpack[_RequestOptions],
    ) -> Any:
        async with self.session.post(url, **kwargs) as response:
            response.raise_for_status()
            return await response.json(encoding="utf-8")

    @retryable_client_session
    async def download_image(
        self,
        url: StrOrURL,
        **kwargs: Unpack[_RequestOptions],
    ) -> tuple[str, bytes]:
        async with self.session.get(url, **kwargs) as response:
            response.raise_for_status()
            return (response.content_type, await response.read())

    def fetch_manga_listing(self) -> AsyncIterable[MangaListing]:
        try:
            return self.on_fetch_manga_listing()
        except FetchError:
            raise
        except Exception as error:
            raise FetchError() from error

    @abstractmethod
    def on_fetch_manga_listing(self) -> AsyncIterable[MangaListing]:
        raise NotImplementedError()

    async def fetch_manga_detail(
        self, manga_id: str, link: str
    ) -> MangaDetail:
        try:
            return await self.on_fetch_manga_detail(manga_id, link)
        except FetchError:
            raise
        except SeriesNotFoundError:
            raise
        except Exception as error:
            raise FetchError() from error

    @abstractmethod
    async def on_fetch_manga_detail(
        self, manga_id: str, link: str
    ) -> MangaDetail:
        raise NotImplementedError()

    async def fetch_manga_pages(
        self,
        manga_id: str,
        manga_link: str,
        chapter_id: str,
        chapter_link: str,
    ) -> Sequence[MangaPage]:
        try:
            return await self.on_fetch_manga_pages(
                manga_id, manga_link, chapter_id, chapter_link
            )
        except FetchError:
            raise
        except Exception as error:
            raise FetchError() from error

    @abstractmethod
    async def on_fetch_manga_pages(
        self,
        manga_id: str,
        manga_link: str,
        chapter_id: str,
        chapter_link: str,
    ) -> Sequence[MangaPage]:
        raise NotImplementedError()

    async def fetch_manga_image(self, page: MangaPage) -> MangaImage:
        try:
            return await self.on_fetch_manga_image(page)
        except FetchError:
            raise
        except Exception as error:
            raise FetchError() from error

    async def on_fetch_manga_image(self, page: MangaPage) -> MangaImage:
        content_type, data = await self.download_image(page.image_link)
        filename = f"{page.page_number:03d}{mimetypes.guess_extension(content_type, False)}"
        return MangaImage(filename, data)
