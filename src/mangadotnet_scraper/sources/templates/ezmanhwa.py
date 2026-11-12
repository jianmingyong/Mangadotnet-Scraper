from collections.abc import AsyncGenerator, Sequence
from typing import Final, TypedDict, Unpack, override

from asynciolimiter import Limiter

from mangadotnet_scraper.camoufox_utils import get_default_user_agent
from mangadotnet_scraper.config import Config
from mangadotnet_scraper.sources import BaseSourceProvider
from mangadotnet_scraper.sources.base import (
    Chapter,
    ImageRequest,
    Manga,
    Page,
    SourceInfo,
)
from mangadotnet_scraper.utilities import (
    clean_alt_titles,
    clean_chapter_title,
    dict_get_recursive,
)


class MangaListingResponse(TypedDict):
    data: Sequence[MangaListingResponseData]
    totalItems: int
    totalPages: int
    current: int
    next: int


class MangaListingResponseData(TypedDict):
    id: int
    slug: str
    title: str
    alternativeTitles: str | None
    type: str


class MangaDetailResponse(TypedDict):
    title: str
    alternativeTitles: str | None


class MangaChapterResponse(TypedDict):
    data: Sequence[MangaChapterResponseData]
    totalItems: int
    nextCursor: str | None
    hasMore: bool


class MangaChapterResponseData(TypedDict):
    id: int
    slug: str
    number: float
    isFree: bool
    title: str | None


class MangaPageResponse(TypedDict):
    images: list[MangaPageResponseImage]


class MangaPageResponseImage(TypedDict):
    url: str
    order: int
    width: int
    height: int


class EzManhwaTemplate(BaseSourceProvider):
    group_name: Final[str]

    def __init__(
        self,
        config: Config,
        group_name: str,
        **kwargs: Unpack[SourceInfo],
    ) -> None:
        super().__init__(config, **kwargs)

        self.group_name = group_name

    async def fetch_listing(self, page: int = 1) -> MangaListingResponse:
        return await self.client.get_json(
            "/api/v1/series",
            params={"page": page, "perPage": 100, "sort": "newest"},
        )

    @override
    async def initialize_client(self) -> None:
        if self.user_agent is None:
            self.user_agent = (
                await get_default_user_agent()
                or "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:159.0) Gecko/20100101 Firefox/159.0"
            )

        if self.headers is None:
            self.headers = {
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/",
            }

        if self.limiter is None:
            self.limiter = Limiter(1, max_burst=60)

        await super().initialize_client()

    @override
    async def close(self) -> None:
        await super().close()

        if self.limiter is not None:
            self.limiter.close()

    async def get_chapters(
        self, slug_id: str, cursor: str | None
    ) -> MangaChapterResponse:
        return await self.client.get_json(
            f"/api/v2/series/{slug_id}/chapters",
            params={"limit": 100, "sort": "asc"}
            if cursor is None
            else {"limit": 100, "sort": "asc", "cursor": cursor},
        )

    @override
    async def _on_get_manga_list(self) -> AsyncGenerator[Manga]:
        page = 1
        has_next_page = True

        while has_next_page:
            json = await self.fetch_listing(page)

            for data in dict_get_recursive(json, "data", default=[]):
                if (
                    dict_get_recursive(data, "type") != "NOVEL"
                    and dict_get_recursive(data, "slug") != ""
                ):
                    id: int | None = dict_get_recursive(data, "id")
                    title: str | None = dict_get_recursive(data, "title")
                    slug: str | None = dict_get_recursive(data, "slug")

                    if id is None or title is None or slug is None:
                        continue

                    yield Manga(
                        id=str(id),
                        title=title,
                        link=f"{self.base_url}/series/{slug}",
                    )

            has_next_page = page * 100 < dict_get_recursive(
                json, "totalItems", default=0
            )
            page += 1

    @override
    async def _on_get_manga_update(
        self,
        manga: Manga,
        need_details: bool = True,
        need_chapters: bool = True,
    ) -> Manga:
        new_manga = manga.copy()
        slug_id = manga.link[manga.link.rindex("/") + 1 :]

        if need_details:
            detail_json: MangaDetailResponse = await self.client.get_json(
                f"/api/v1/series/{slug_id}"
            )

            new_manga.title = dict_get_recursive(
                detail_json, "title", default=new_manga.title
            )

            alt_titles_str: str | None = dict_get_recursive(
                detail_json, "alternativeTitles"
            )

            new_manga.alt_titles = clean_alt_titles(alt_titles_str)

        if need_chapters:
            chapters = []

            has_more = True
            cursor = None

            while has_more:
                chapters_json = await self.get_chapters(slug_id, cursor)

                for data in dict_get_recursive(
                    chapters_json, "data", default=[]
                ):
                    if dict_get_recursive(data, "isFree", default=True):
                        inner_title: str | None = dict_get_recursive(
                            data, "title"
                        )
                        inner_number: float | None = dict_get_recursive(
                            data, "number"
                        )
                        slug: str | None = dict_get_recursive(data, "slug")
                        id: int | None = dict_get_recursive(data, "id")

                        if inner_number is None or slug is None or id is None:
                            continue

                        chapters.append(
                            Chapter(
                                id=str(id),
                                language="en",
                                group=self.group_name,
                                type="chapter",
                                volume_number=None,
                                chapter_number=inner_number,
                                title=clean_chapter_title(
                                    inner_number, inner_title
                                ),
                                link=f"{self.base_url}/series/{slug_id}/{slug}",
                            )
                        )

                has_more = dict_get_recursive(
                    chapters_json, "hasMore", default=False
                )
                cursor = dict_get_recursive(chapters_json, "nextCursor")

            new_manga.chapters = chapters

        return new_manga

    @override
    async def _on_get_page_list(
        self, manga: Manga, chapter: Chapter
    ) -> Sequence[Page]:
        manga_slug = manga.link[manga.link.rfind("/") + 1 :]
        chapter_slug = chapter.link[chapter.link.rfind("/") + 1 :]

        manga_pages = []

        json: MangaPageResponse = await self.client.get_json(
            f"/api/v1/series/{manga_slug}/chapters/{chapter_slug}"
        )

        for image in dict_get_recursive(json, "images", default=[]):
            order: int | None = dict_get_recursive(image, "order")
            url: str | None = dict_get_recursive(image, "url")

            if order is None or url is None:
                continue

            manga_pages.append(Page(order, url))

        return manga_pages

    @override
    async def _on_get_image_request(self, page: Page) -> ImageRequest:
        return ImageRequest(headers={"Referer": f"{self.base_url}/"})
