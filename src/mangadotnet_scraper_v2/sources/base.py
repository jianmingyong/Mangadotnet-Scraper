from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any, Final, Literal, Self

from aiohttp import ClientSession
from camoufox import AsyncCamoufox

from mangadotnet_scraper_v2.config import Config


@dataclass
class Manga:
    id: str
    title: str
    link: str
    alt_titles: Sequence[str] = []
    chapters: Sequence[Chapter] = []


@dataclass
class Chapter:
    id: str
    language: str
    group: str
    type: Literal["chapter", "volume"]
    volume_number: float | None
    chapter_number: float | None
    title: str
    link: str


@dataclass(frozen=True)
class Page:
    page_number: int
    image_link: str
    context_data: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class Image:
    filename: str
    data: bytes


class SourceError(Exception):
    """Base class for source errors"""


class BaseSourceProvider(AbstractAsyncContextManager):
    config: Final[Config]

    source_id: Final[str]
    display_name: Final[str]
    languages: Final[Sequence[str]]
    version: Final[int]

    base_urls: Final[Sequence[str]]
    user_agent: Final[str | None]

    client: ClientSession
    browser: AsyncCamoufox

    def __init__(
        self,
        config: Config,
        source_id: str,
        display_name: str,
        languages: Sequence[str] | None,
        version: int,
        base_urls: Sequence[str],
        user_agent: str | None = None,
    ) -> None:
        self.config = config

        self.source_id = source_id
        self.display_name = display_name
        self.languages = languages if languages is not None else ["en"]
        self.version = version

        self.base_urls = base_urls
        self.user_agent = user_agent

    async def __aenter__(self) -> Self:
        await self.initialize()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    @classmethod
    def create_provider(cls, config: Config) -> Self:
        if cls is BaseSourceProvider:
            raise ValueError("Cannot initialize base module.")

        # pyrefly: ignore [missing-argument]
        return cls(config)

    async def initialize(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def get_manga_list(self) -> AsyncGenerator[Manga]:
        try:
            async for list in self._on_get_manga_list():
                yield list
        except Exception as error:
            raise SourceError("Error fetching manga list") from error

    async def get_manga_update(
        self,
        manga: Manga,
        need_details: bool = True,
        need_chapters: bool = True,
    ) -> Manga:
        try:
            return await self._on_get_manga_update(
                manga, need_details, need_chapters
            )
        except Exception as error:
            raise SourceError("Error fetching manga update") from error

    async def get_page_list(
        self, manga: Manga, chapter: Chapter
    ) -> Sequence[Page]:
        try:
            pages = await self._on_get_page_list(manga, chapter)
            seen: set[int] = set()

            for page in pages:
                if page.page_number in seen:
                    raise SourceError(
                        "Duplicate page number found. This might be a broken chapter."
                    )
                else:
                    seen.add(page.page_number)

            return pages
        except Exception as error:
            raise SourceError("Error fetching page list") from error

    async def get_manga_image(self, page: Page) -> Image:
        try:
            return await self._on_get_manga_image(page)
        except Exception as error:
            raise SourceError("Error fetching manga image") from error

    async def handle_manga_migration(self, manga: Manga) -> Manga:
        try:
            return await self._on_handle_manga_migration(manga)
        except Exception as error:
            raise SourceError("Error handling manga migration") from error

    def _on_get_manga_list(self) -> AsyncGenerator[Manga]:
        raise NotImplementedError()

    async def _on_get_manga_update(
        self,
        manga: Manga,
        need_details: bool = True,
        need_chapters: bool = True,
    ) -> Manga:
        raise NotImplementedError()

    async def _on_get_page_list(
        self, manga: Manga, chapter: Chapter
    ) -> Sequence[Page]:
        raise NotImplementedError()

    async def _on_get_manga_image(self, page: Page) -> Image:
        raise NotImplementedError()

    async def _on_handle_manga_migration(self, manga: Manga) -> Manga:
        raise NotImplementedError()
