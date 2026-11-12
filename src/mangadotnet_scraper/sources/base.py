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
    Unpack,
    cast,
    override,
)

from asynciolimiter import LeakyBucketLimiter, Limiter, StrictLimiter
from camoufox import AsyncCamoufox
from playwright.async_api import Browser, Error

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
    page: int
    link: str
    context: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ImageRequest:
    cookies: Mapping[str, str] | None = None
    headers: Mapping[str, str] | None = None


class SourceError(Exception):
    """Base class for source errors"""


class SourceInfo(TypedDict):
    source_id: Required[str]
    name: Required[str]
    version: Required[int]
    languages: Required[Sequence[str]]

    base_url: NotRequired[str]
    base_urls: NotRequired[Sequence[str]]

    base_api_url: NotRequired[str]
    base_api_urls: NotRequired[Sequence[str]]
    user_agent: NotRequired[str]
    headers: NotRequired[Mapping[str, str]]
    cookies: NotRequired[Mapping[str, str]]
    limiter: NotRequired[LeakyBucketLimiter | Limiter | StrictLimiter]


class BaseSourceProvider(AbstractAsyncContextManager):
    config: Final[Config]

    source_id: Final[str]
    name: Final[str]
    version: Final[int]
    languages: Final[Sequence[str]]

    base_url: str
    base_urls: Final[Sequence[str]]

    base_api_url: str | None
    base_api_urls: Sequence[str] | None
    user_agent: str | None
    headers: Mapping[str, str] | None
    cookies: Mapping[str, str] | None
    limiter: LeakyBucketLimiter | Limiter | StrictLimiter | None

    settings: Mapping[str, Any]

    client: HttpClient

    _camoufox: AsyncCamoufox | None
    _browser: Browser | None

    def __init__(
        self,
        config: Config,
        **kwargs: Unpack[SourceInfo],
    ) -> None:
        self.config = config

        self.source_id = kwargs["source_id"]
        self.name = kwargs["name"]
        self.version = kwargs["version"]
        self.languages = kwargs["languages"]

        if "base_url" not in kwargs and "base_urls" not in kwargs:
            raise SourceError(
                "Source cannot be initilized as base_url or base_urls must be defined"
            )

        self.base_urls = kwargs.get("base_urls", [kwargs["base_url"]])

        self.base_api_url = kwargs.get("base_api_url")
        self.base_api_urls = kwargs.get("base_api_urls")
        self.user_agent = kwargs.get("user_agent")
        self.headers = kwargs.get("headers")
        self.cookies = kwargs.get("cookies")
        self.limiter = kwargs.get("limiter")

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

        if self.base_api_urls is not None:
            self.base_api_url = self.settings.get(
                "base_api_url", self.base_api_urls[0]
            )

        await self.initialize_client()

        self._camoufox = None
        self._browser = None

    async def initialize_client(self) -> None:
        base_url = (
            self.base_api_url
            if self.base_api_url is not None
            else self.base_url
        )

        self.client = HttpClient(
            base_url, self.user_agent, self.headers, self.cookies, self.limiter
        )

    async def get_browser(self) -> Browser:
        if self._camoufox is None and self._browser is None:
            try:
                self._camoufox = create_browser()
                self._browser = cast(Browser, await self._camoufox.start())
            except Error:
                if self._camoufox is not None:
                    await self._camoufox.__aexit__()
                self._camoufox = None
                raise

        return cast(Browser, self._browser)

    async def close(self) -> None:
        if self.limiter is not None:
            self.limiter.close()

        if self.client is not None:
            await self.client.close()

        if self._browser is not None:
            await self._browser.close()
            self._browser = None

        if self._camoufox is not None:
            await self._camoufox.__aexit__()
            self._camoufox = None

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
                if page.page in seen:
                    raise SourceError(
                        "Duplicate page number found. This might be a broken chapter."
                    )
                else:
                    seen.add(page.page)

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
