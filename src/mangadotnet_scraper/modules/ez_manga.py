from collections.abc import AsyncIterable, Collection
from typing import TypedDict, override

from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.base import BaseModule, MangaChapter, MangaDetail, MangaListing, MangaPage
from mangadotnet_scraper.utilities import clean_string, safe_dict_get


class EzMangaModule(BaseModule):
    _BASE_URL = "https://ezmanga.org"
    _BASE_API_URL = "https://vapi.ezmanga.org"

    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        super().__init__(
            config,
            "ez_manga",
            "Ezmanga",
            self._BASE_URL,
            self._BASE_API_URL,
            {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0"},
        )

    class MangaListingResponse(TypedDict):
        data: Collection[EzMangaModule.MangaListingResponseData]
        totalItems: int
        totalPages: int
        current: int
        next: int

    class MangaListingResponseData(TypedDict):
        id: int
        slug: str
        title: str
        alternativeTitles: str
        type: str

    @override
    async def fetch_manga_listing(self) -> AsyncIterable[MangaListing]:
        async def fetch_listing(page: int = 1) -> self.MangaListingResponse:
            return await self.get_json(
                "/api/v1/series",
                params={"page": page, "perPage": 100, "sort": "newest"},
            )

        page = 1
        has_next_page = True

        while has_next_page:
            json = await fetch_listing(page)

            for data in safe_dict_get(json, "data", type=Collection[self.MangaListingResponseData], default=[]):
                if safe_dict_get(data, "type") != "NOVEL" and safe_dict_get(data, "slug") != "":
                    id = safe_dict_get(data, "id", type=int)
                    title = safe_dict_get(data, "title", type=str)
                    slug = safe_dict_get(data, "slug", type=str)

                    if id is None or title is None or slug is None:
                        continue

                    yield MangaListing(str(id), clean_string(title), clean_string(f"{self._BASE_URL}/series/{slug}"))

            has_next_page = page * 100 < safe_dict_get(json, "totalItems", type=int, default=0)
            page += 1

    class MangaDetailResponse(TypedDict):
        title: str
        alternativeTitles: str

    class MangaChapterResponse(TypedDict):
        data: Collection[EzMangaModule.MangaChapterResponseData]
        totalItems: int
        nextCursor: str | None
        hasMore: bool

    class MangaChapterResponseData(TypedDict):
        id: int
        slug: str
        number: float
        isFree: bool
        title: str | None

    @override
    async def fetch_manga_detail(self, manga_id: str, link: str) -> MangaDetail:
        slug_id = link[link.rindex("/") + 1 :]

        detail_json: self.MangaDetailResponse = await self.get_json(f"/api/v1/series/{slug_id}")

        title = clean_string(safe_dict_get(detail_json, "title", type=str, default=""))
        alt_titles = clean_string(safe_dict_get(detail_json, "alternativeTitles", type=str, default=""))

        chapters = []

        async def get_chapters(cursor: str | None):
            return await self.get_json(
                f"/api/v2/series/{slug_id}/chapters",
                params={"limit": 100, "sort": "asc"}
                if cursor is None
                else {"limit": 100, "sort": "asc", "cursor": cursor},
            )

        has_more = True
        cursor = None

        while has_more:
            chapters_json: self.MangaChapterResponse = await get_chapters(cursor)

            for data in safe_dict_get(
                chapters_json, "data", type=Collection[self.MangaChapterResponseData], default=[]
            ):
                if safe_dict_get(data, "isFree", type=bool, default=True):
                    inner_title = safe_dict_get(data, "title", type=str)
                    inner_number = safe_dict_get(data, "number", type=float)
                    slug = safe_dict_get(data, "slug", type=str)
                    id = safe_dict_get(data, "id", type=int)

                    if inner_number is None or slug is None or id is None:
                        continue

                    chapters.append(
                        MangaChapter(
                            "en",
                            self.display_name,
                            "chapter",
                            inner_number,
                            None,
                            inner_title
                            if inner_title is not None and inner_title != "" and inner_title != inner_number
                            else f"Chapter {inner_number}",
                            f"{self._BASE_URL}/series/{slug_id}/{slug}",
                            str(id),
                        )
                    )

            has_more = safe_dict_get(chapters_json, "hasMore", type=bool, default=False)
            cursor = safe_dict_get(chapters_json, "nextCursor", type=str)

        return MangaDetail(title, [alt_titles], chapters)

    class MangaPageResponse(TypedDict):
        images: list[EzMangaModule.MangaPageResponseImage]

    class MangaPageResponseImage(TypedDict):
        url: str
        order: int
        width: int
        height: int

    @override
    async def fetch_manga_pages(
        self, manga_id: str, manga_link: str, chapter_id: str, chapter_link: str
    ) -> list[MangaPage]:
        manga_slug = manga_link[manga_link.rfind("/") + 1 :]
        chapter_slug = chapter_link[chapter_link.rfind("/") + 1 :]

        manga_pages: list[MangaPage] = []

        json: self.MangaPageResponse = await self.get_json(f"/api/v1/series/{manga_slug}/chapters/{chapter_slug}")

        for image in safe_dict_get(json, "images", type=Collection[self.MangaPageResponseImage], default=[]):
            order = safe_dict_get(image, "order", type=int)
            url = safe_dict_get(image, "url", type=str)

            if order is None or url is None:
                continue

            manga_pages.append(MangaPage(order, url, None))

        return manga_pages
