from collections.abc import AsyncIterable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Final, Literal, Self

from mangadotnet_scraper.config import MangaDotNetScraperConfig


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
    _config: Final[MangaDotNetScraperConfig]

    module_id: Final[str]
    display_name: Final[str]

    fetch_concurrency: int
    download_concurrency: int
    upload_concurrency: int

    def __init__(self, config: MangaDotNetScraperConfig, module_id: str, display_name: str) -> None:
        self._config = config
        self.module_id = module_id
        self.display_name = display_name
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
        return

    async def close(self) -> None:
        return

    def fetch_manga_listing(self) -> AsyncIterable[MangaListing]:
        raise NotImplementedError()

    async def fetch_manga_detail(self, manga_id: str, link: str) -> MangaDetail:
        raise NotImplementedError()

    async def fetch_manga_pages(
        self, manga_id: str, manga_link: str, chapter_id: str, chapter_link: str
    ) -> list[MangaPage]:
        raise NotImplementedError()

    async def fetch_manga_image(self, page: MangaPage) -> MangaImage:
        raise NotImplementedError()
