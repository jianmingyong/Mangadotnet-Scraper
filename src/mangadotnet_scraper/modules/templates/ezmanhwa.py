import re
from collections.abc import AsyncIterable, Sequence
from typing import Final, TypedDict, Unpack, override

from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.base import (
    BaseModule,
    BaseModuleArgs,
    MangaChapter,
    MangaDetail,
    MangaListing,
    MangaPage,
)
from mangadotnet_scraper.utilities import clean_string, dict_get_recursive


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


class EzManhwaTemplate(BaseModule):
    group_name: Final[str]

    def __init__(
        self,
        config: MangaDotNetScraperConfig,
        group_name: str,
        **kwargs: Unpack[BaseModuleArgs],
    ) -> None:
        super().__init__(config, **kwargs)

        self.group_name = group_name

    @override
    async def on_fetch_manga_listing(self) -> AsyncIterable[MangaListing]:
        async def fetch_listing(page: int = 1) -> MangaListingResponse:
            return await self.get_json(
                "/api/v1/series",
                params={"page": page, "perPage": 100, "sort": "newest"},
            )

        page = 1
        has_next_page = True

        while has_next_page:
            json = await fetch_listing(page)

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

                    yield MangaListing(
                        str(id),
                        clean_string(title),
                        clean_string(f"{self.base_url}/series/{slug}"),
                    )

            has_next_page = page * 100 < dict_get_recursive(
                json, "totalItems", default=0
            )
            page += 1

    @override
    async def on_fetch_manga_detail(
        self, manga_id: str, link: str
    ) -> MangaDetail:
        slug_id = link[link.rindex("/") + 1 :]

        detail_json: MangaDetailResponse = await self.get_json(
            f"/api/v1/series/{slug_id}"
        )

        title = clean_string(
            dict_get_recursive(detail_json, "title", default="")
        )

        alt_titles_str: str | None = dict_get_recursive(
            detail_json, "alternativeTitles"
        )

        if alt_titles_str is None:
            alt_titles = []
        else:
            alt_titles = [
                clean_string(x)
                for x in re.split(
                    r"[/\\\r\n]+",
                    alt_titles_str,
                )
                if len(clean_string(x)) > 0
            ]

        chapters = []

        async def get_chapters(
            cursor: str | None,
        ) -> MangaChapterResponse:
            return await self.get_json(
                f"/api/v2/series/{slug_id}/chapters",
                params={"limit": 100, "sort": "asc"}
                if cursor is None
                else {"limit": 100, "sort": "asc", "cursor": cursor},
            )

        has_more = True
        cursor = None

        while has_more:
            chapters_json = await get_chapters(cursor)

            for data in dict_get_recursive(chapters_json, "data", default=[]):
                if dict_get_recursive(data, "isFree", default=True):
                    inner_title: str | None = dict_get_recursive(data, "title")
                    inner_number: float | None = dict_get_recursive(
                        data, "number"
                    )
                    slug: str | None = dict_get_recursive(data, "slug")
                    id: int | None = dict_get_recursive(data, "id")

                    if inner_number is None or slug is None or id is None:
                        continue

                    chapters.append(
                        MangaChapter(
                            self.language,
                            self.group_name,
                            "chapter",
                            inner_number,
                            None,
                            inner_title
                            if inner_title is not None
                            and inner_title != ""
                            and inner_title != inner_number
                            else f"Chapter {inner_number}",
                            f"{self.base_url}/series/{slug_id}/{slug}",
                            str(id),
                        )
                    )

            has_more = dict_get_recursive(
                chapters_json, "hasMore", default=False
            )
            cursor = dict_get_recursive(chapters_json, "nextCursor")

        return MangaDetail(title, alt_titles, chapters)

    @override
    async def on_fetch_manga_pages(
        self,
        manga_id: str,
        manga_link: str,
        chapter_id: str,
        chapter_link: str,
    ) -> list[MangaPage]:
        manga_slug = manga_link[manga_link.rfind("/") + 1 :]
        chapter_slug = chapter_link[chapter_link.rfind("/") + 1 :]

        manga_pages: list[MangaPage] = []

        json: MangaPageResponse = await self.get_json(
            f"/api/v1/series/{manga_slug}/chapters/{chapter_slug}"
        )

        for image in dict_get_recursive(json, "images", default=[]):
            order: int | None = dict_get_recursive(image, "order")
            url: str | None = dict_get_recursive(image, "url")

            if order is None or url is None:
                continue

            manga_pages.append(MangaPage(order, url, None))

        return manga_pages
