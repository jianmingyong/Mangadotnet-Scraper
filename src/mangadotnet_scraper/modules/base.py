import mimetypes
from collections.abc import AsyncIterable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Final, Literal, Self

from aiohttp import ClientSession
from aiohttp.typedefs import Query

from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.network import create_client, retryable_client_session


@dataclass(frozen=True)
class MangaListing:
    manga_id: str
    title: str
    link: str


@dataclass(frozen=True)
class MangaDetail:
    title: str
    alt_titles: list[str]
    chapters: list[MangaChapter]


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
    link: str
    data: dict[str, Any] | None


@dataclass(frozen=True)
class MangaImage:
    filename: str
    data: bytes


class BaseModule(AbstractAsyncContextManager):
    config: Final[MangaDotNetScraperConfig]

    module_id: Final[str]
    display_name: Final[str]

    base_url: Final[str]
    base_api_url: Final[str]

    additional_headers: Final[Mapping[str, str] | None]

    fetch_concurrency: int
    download_concurrency: int
    upload_concurrency: int

    session: ClientSession

    def __init__(
        self,
        config: MangaDotNetScraperConfig,
        module_id: str,
        display_name: str,
        base_url: str,
        base_api_url: str | None = None,
        additional_headers: Mapping[str, str] | None = None,
    ) -> None:
        self.config = config

        self.module_id = module_id
        self.display_name = display_name

        self.base_url = base_url
        self.base_api_url = base_api_url if base_api_url is not None else base_url

        self.additional_headers = additional_headers

        self.fetch_concurrency = config.fetch_concurrency
        self.download_concurrency = config.download_concurrency
        self.upload_concurrency = config.upload_concurrency

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
        headers = {"Origin": self.base_url}

        if self.additional_headers is not None:
            headers.update(self.additional_headers)

        self.session = create_client(base_url=self.base_api_url, headers=headers)

    async def close(self) -> None:
        await self.session.close()

    @retryable_client_session
    async def get_html(self, url: str, params: Query = None) -> str:
        async with self.session.get(url, params=params) as response:
            response.raise_for_status()
            return await response.text("utf-8")

    @retryable_client_session
    async def get_json(self, url: str, params: Query = None) -> Any:
        async with self.session.get(url, params=params) as response:
            response.raise_for_status()
            return await response.json()

    @retryable_client_session
    async def download_image(self, url: str, params: Query = None) -> tuple[str, bytes]:
        async with self.session.get(url, params=params) as response:
            response.raise_for_status()
            return (response.content_type, await response.read())

    def fetch_manga_listing(self) -> AsyncIterable[MangaListing]:
        raise NotImplementedError()

    async def fetch_manga_detail(self, manga_id: str, link: str) -> MangaDetail:
        raise NotImplementedError()

    async def fetch_manga_pages(
        self, manga_id: str, manga_link: str, chapter_id: str, chapter_link: str
    ) -> list[MangaPage]:
        raise NotImplementedError()

    async def fetch_manga_image(self, page: MangaPage) -> MangaImage:
        content_type, data = await self.download_image(page.link)
        filename = f"{page.page_number:03d}{mimetypes.guess_extension(content_type, False)}"
        return MangaImage(filename, data)
