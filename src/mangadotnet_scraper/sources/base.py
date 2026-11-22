from abc import abstractmethod
from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import (
    Any,
    Final,
    Literal,
    NotRequired,
    Protocol,
    Required,
    Self,
    TypedDict,
    Unpack,
    final,
    override,
)

from asynciolimiter import LeakyBucketLimiter, Limiter, StrictLimiter

from mangadotnet_scraper.camoufox_utils import Browser
from mangadotnet_scraper.config import Config
from mangadotnet_scraper.network import (
    HttpClient,
    create_http_client,
    retryable_client_method,
)
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

    @classmethod
    def from_dict(cls, dict: Mapping[str, Any]) -> Chapter:
        return Chapter(
            id=dict["id"],
            language=dict["language"],
            group=dict["group"],
            type=dict["type"],
            volume_number=dict.get("volume_number"),
            chapter_number=dict.get("chapter_number"),
            title=dict["title"],
            link=dict["link"],
        )

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
    url: str
    cookies: Mapping[str, str] | None = None
    headers: Mapping[str, str] | None = None


class SourceError(Exception):
    """Base class for source errors"""


class SourceInfo(TypedDict):
    config: NotRequired[Config]
    browser: NotRequired[Browser]

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


class SourceProviderInterface(Protocol):
    source_id: Final[str]
    name: Final[str]
    version: Final[int]
    languages: Final[Sequence[str]]

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, *args) -> None: ...

    def get_manga_list(self) -> AsyncGenerator[Manga]: ...

    async def get_manga_update(
        self,
        manga: Manga,
        need_details: bool = True,
        need_chapters: bool = True,
    ) -> Manga: ...

    async def get_page_list(
        self,
        manga: Manga,
        chapter: Chapter,
    ) -> Sequence[Page]: ...

    def get_image_request(self, page: Page) -> ImageRequest: ...

    async def download_image(self, request: ImageRequest) -> bytes: ...

    async def process_page_image(self, image: bytes, page: Page) -> bytes: ...

    async def handle_manga_migration(self, manga: Manga) -> Manga: ...


class BaseSourceProvider(AbstractAsyncContextManager):
    config: Final[Config]
    browser: Final[Browser]

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

    def __init__(
        self,
        **kwargs: Unpack[SourceInfo],
    ) -> None:
        self.config = kwargs["config"]
        self.browser = kwargs["browser"]

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
    def create_provider(
        cls, config: Config, browser: Browser, **kwargs
    ) -> Self:
        if cls is BaseSourceProvider:
            raise ValueError("Cannot initialize base module.")

        return cls(config=config, browser=browser, **kwargs)

    @final
    async def initialize(self) -> None:
        self.settings = self.config.get_source_config(self.source_id)
        self.base_url = self.settings.get("base_url", self.base_urls[0])

        if self.base_api_urls is not None:
            self.base_api_url = self.base_api_urls[
                self.base_urls.index(self.base_url)
            ]

        await self._on_initialize()

        base_url = (
            self.base_api_url
            if self.base_api_url is not None
            else self.base_url
        )

        self.client = create_http_client(
            base_url, self.user_agent, self.headers, self.cookies, self.limiter
        )

    async def close(self) -> None:
        if self.limiter is not None:
            self.limiter.close()

        if self.client is not None:
            await self.client.close()

    @final
    @retryable_client_method
    async def get_html(
        self, url: str, params: Mapping[str, Any] | None = None, **kwargs
    ) -> str:
        async with await self.client.get(url, params, **kwargs) as response:
            response.raise_for_status()
            return await response.text()

    @final
    @retryable_client_method
    async def get_json(
        self, url: str, params: Mapping[str, Any] | None = None, **kwargs
    ) -> Any:
        async with await self.client.get(url, params, **kwargs) as response:
            response.raise_for_status()
            return await response.json()

    @final
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

    @final
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

    @final
    async def get_page_list(
        self,
        manga: Manga,
        chapter: Chapter,
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

    @final
    def get_image_request(self, page: Page) -> ImageRequest:
        try:
            return self._on_get_image_request(page)
        except Exception as error:
            raise SourceError("Error fetching image request") from error

    @final
    @retryable_client_method
    async def download_image(self, request: ImageRequest) -> bytes:
        async with await self.client.get(
            request.url, headers=request.headers, cookies=request.cookies
        ) as response:
            response.raise_for_status()
            return await response.read()

    @final
    async def process_page_image(self, image: bytes, page: Page) -> bytes:
        try:
            return await self._on_process_page_image(image, page)
        except Exception as error:
            raise SourceError("Error processing page image") from error

    @final
    async def handle_manga_migration(self, manga: Manga) -> Manga:
        try:
            return await self._on_handle_manga_migration(manga)
        except Exception as error:
            raise SourceError("Error handling manga migration") from error

    async def _on_initialize(self) -> None:
        pass

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
        self,
        manga: Manga,
        chapter: Chapter,
    ) -> Sequence[Page]: ...

    def _on_get_image_request(self, page: Page) -> ImageRequest:
        return ImageRequest(page.link)

    async def _on_process_page_image(self, image: bytes, page: Page) -> bytes:
        return image

    async def _on_handle_manga_migration(self, manga: Manga) -> Manga:
        return manga
