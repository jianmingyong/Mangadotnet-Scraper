from abc import abstractmethod
from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import (
    Any,
    Final,
    Literal,
    NotRequired,
    Required,
    Self,
    TypedDict,
    cast,
    override,
)

from camoufox import AsyncCamoufox
from playwright.async_api import Browser, BrowserContext, Error

from mangadotnet_scraper.camoufox_utils import create_browser
from mangadotnet_scraper.config import Config
from mangadotnet_scraper.network import HttpClient
from mangadotnet_scraper.utilities import clean_string, normalize_url


@dataclass
class Manga:
    id: str
    title: str
    link: str
    alt_titles: Sequence[str] = field(default_factory=list)
    chapters: Sequence[Chapter] = field(default_factory=list)

    def copy(self) -> Manga:
        return Manga(
            self.id,
            self.title,
            self.link,
            [t for t in self.alt_titles],
            [c.copy() for c in self.chapters],
        )


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

    def copy(self) -> Chapter:
        return Chapter(
            self.id,
            self.language,
            self.group,
            self.type,
            self.volume_number,
            self.chapter_number,
            self.title,
            self.link,
        )


@dataclass(frozen=True)
class Page:
    page_number: int
    image_link: str
    context_data: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ImageRequest:
    cookies: Mapping[str, str] | None = None
    headers: Mapping[str, str] | None = None


@dataclass(frozen=True)
class Image:
    filename: str
    data: bytes


class SourceError(Exception):
    """Base class for source errors"""


class SourceInfo(TypedDict):
    source_id: Required[str]
    name: Required[str]
    version: Required[int]
    languages: Required[Sequence[str]]

    base_url: NotRequired[str | None]
    base_urls: NotRequired[Sequence[str] | None]


class BaseSourceProvider(AbstractAsyncContextManager):
    config: Final[Config]

    source_id: Final[str]
    name: Final[str]
    version: Final[int]
    languages: Final[Sequence[str]]

    base_url: str
    base_urls: Final[Sequence[str]]

    settings: Mapping[str, Any]

    client: HttpClient

    _camoufox: AsyncCamoufox | None
    _browser: Browser | None
    _browser_context: BrowserContext | None

    def __init__(
        self,
        config: Config,
        source_id: str,
        name: str,
        languages: Sequence[str],
        version: int,
        base_url: str | None = None,
        base_urls: Sequence[str] | None = None,
    ) -> None:
        self.config = config

        self.source_id = source_id
        self.name = name
        self.version = version
        self.languages = languages

        if base_url is None and base_urls is None:
            raise SourceError(
                "Source cannot be initilized as base_url or base_urls must be defined"
            )

        self.base_urls = (
            base_urls if base_urls is not None else [cast(str, base_url)]
        )

    @override
    async def __aenter__(self) -> Self:
        await self.initialize()
        return self

    @override
    async def __aexit__(self, *args) -> None:
        await self.close()

    @classmethod
    def create_provider(cls, config: Config) -> Self:
        if cls is BaseSourceProvider:
            raise ValueError("Cannot initialize base module.")

        # pyrefly: ignore [missing-argument]
        return cls(config)

    async def initialize(self) -> None:
        self.settings = self.config.get_source_config(self.source_id)
        self.base_url = self.settings.get("base_url", self.base_urls[0])

        self.client = HttpClient(self.base_url)

        self._camoufox = None
        self._browser = None
        self._browser_context = None

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()

        if self._browser_context is not None:
            await self._browser_context.close()

        if self._browser is not None:
            await self._browser.close()

        if self._camoufox is not None:
            await self._camoufox.__aexit__()

    async def get_browser_context(self) -> BrowserContext:
        if self._browser_context is None:
            self._camoufox = (
                create_browser() if self._camoufox is None else self._camoufox
            )

            try:
                self._browser = (
                    cast(Browser, await self._camoufox.start())
                    if self._browser is None
                    else self._browser
                )
                self._browser_context = await self._browser.new_context()
            except Error:
                await self._camoufox.__aexit__()
                raise

        return self._browser_context

    async def get_manga_list(self) -> AsyncGenerator[Manga]:
        try:
            async for list in self._on_get_manga_list():
                list.id = clean_string(list.id)
                list.title = clean_string(list.title)
                list.link = normalize_url(
                    clean_string(list.link), self.base_url
                )
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
            result = await self._on_get_manga_update(
                manga, need_details, need_chapters
            )

            result.id = clean_string(result.id)
            result.title = clean_string(result.title)
            result.alt_titles = [clean_string(x) for x in result.alt_titles]
            result.link = normalize_url(result.link, self.base_url)

            for chapter in result.chapters:
                chapter.id = clean_string(chapter.id)
                chapter.language = clean_string(chapter.language)
                chapter.group = clean_string(chapter.group)
                chapter.title = clean_string(chapter.title)
                chapter.link = normalize_url(chapter.link, self.base_url)

            return result
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

    async def get_image_request(self, page: Page) -> ImageRequest:
        try:
            return await self._on_get_image_request(page)
        except Exception as error:
            raise SourceError("Error fetching image request") from error

    async def process_page_image(self, image: bytes, page: Page) -> bytes:
        try:
            return await self._on_process_page_image(image, page)
        except Exception as error:
            raise SourceError("Error processing page image") from error

    async def handle_manga_migration(self, manga: Manga) -> Manga:
        try:
            return await self._on_handle_manga_migration(manga)
        except Exception as error:
            raise SourceError("Error handling manga migration") from error

    @abstractmethod
    def _on_get_manga_list(self) -> AsyncGenerator[Manga]: ...

    @abstractmethod
    async def _on_get_manga_update(
        self,
        manga: Manga,
        need_details: bool = True,
        need_chapters: bool = True,
    ) -> Manga: ...

    @abstractmethod
    async def _on_get_page_list(
        self, manga: Manga, chapter: Chapter
    ) -> Sequence[Page]: ...

    async def _on_get_image_request(self, page: Page) -> ImageRequest:
        return ImageRequest()

    async def _on_process_page_image(self, image: bytes, page: Page) -> bytes:
        return image

    async def _on_handle_manga_migration(self, manga: Manga) -> Manga:
        return manga
