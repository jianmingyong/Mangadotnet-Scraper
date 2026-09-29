from collections.abc import AsyncIterable, Sequence
from typing import ReadOnly, TypedDict, override

from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.base import BaseModule, MangaChapter, MangaDetail, MangaListing, MangaPage
from mangadotnet_scraper.utilities import clean_string, dict_get_recursive


class PostsResponse(TypedDict):
    posts: ReadOnly[Sequence[PostsResponsePost]]
    totalCount: ReadOnly[int]


class PostsResponsePost(TypedDict):
    id: ReadOnly[int]
    slug: ReadOnly[str]
    postTitle: ReadOnly[str]


class PostResponse(TypedDict):
    post: ReadOnly[PostResponseData]


class PostResponseData(TypedDict):
    postTitle: ReadOnly[str]
    alternativeTitles: ReadOnly[str]


class ChaptersResponse(TypedDict):
    post: ReadOnly[ChaptersResponsePost]
    totalChapterCount: ReadOnly[int]


class ChaptersResponsePost(TypedDict):
    chapters: ReadOnly[Sequence[ChaptersResponsePostChapter]]


class ChaptersResponsePostChapter(TypedDict):
    id: ReadOnly[int]
    slug: ReadOnly[str]
    number: ReadOnly[float]
    title: ReadOnly[str | None]
    isLocked: ReadOnly[bool]


class ChapterResponse(TypedDict):
    chapter: ReadOnly[ChapterResponseObject]


class ChapterResponseObject(TypedDict):
    images: ReadOnly[Sequence[ChapterResponseObjectImages]]


class ChapterResponseObjectImages(TypedDict):
    id: ReadOnly[int]
    url: ReadOnly[str]
    width: ReadOnly[int]
    height: ReadOnly[int]
    order: ReadOnly[int]


class OrionScansModule(BaseModule):
    _BASE_URL = "https://orion-scans.com"
    _BASE_API_URL = "https://api.orion-scans.com"

    def __init__(self, config: MangaDotNetScraperConfig):
        super().__init__(config, "orion_scans", "Orion Scans", self._BASE_URL, self._BASE_API_URL)

    @override
    async def fetch_manga_listing(self) -> AsyncIterable[MangaListing]:
        async def fetch_listing(page: int = 1) -> PostsResponse:
            return await self.get_json(
                "/api/query",
                params={
                    "page": page,
                    "perPage": 100,
                    "view": "archive",
                    "seriesType": "MANHWA,MANHUA,MANGA",
                    "orderBy": "lastChapterAddedAt",
                    "orderDirection": "desc",
                },
            )

        page = 1
        has_next_page = True

        while has_next_page:
            json = await fetch_listing(page)

            for post in dict_get_recursive(json, "posts", default=[]):
                id: int | None = dict_get_recursive(post, "id")
                title: str | None = dict_get_recursive(post, "postTitle")
                slug: str | None = dict_get_recursive(post, "slug")

                if id is None or title is None or slug is None:
                    continue

                yield MangaListing(str(id), clean_string(title), f"{self._BASE_URL}/series/{slug}")

            has_next_page = page * 100 < dict_get_recursive(json, "totalCount", default=0)
            page += 1

    @override
    async def fetch_manga_detail(self, manga_id: str, link: str) -> MangaDetail:
        slug_id = link[link.rindex("/") + 1 :]

        detail_json: PostResponse = await self.get_json("/api/post", params={"postId": manga_id})

        title = clean_string(dict_get_recursive(detail_json, "post", "postTitle", default=""))
        alt_titles = clean_string(dict_get_recursive(detail_json, "post", "alternativeTitles", default=""))

        chapters = []

        chapters_json: ChaptersResponse = await self.get_json("/api/chapters", params={"postId": manga_id})

        for chapter in dict_get_recursive(chapters_json, "post", "chapters", default=[]):
            if dict_get_recursive(chapter, "isLocked", default=False):
                continue

            chapter_title: str | None = dict_get_recursive(chapter, "title")
            chapter_number: float | None = dict_get_recursive(chapter, "number")
            chapter_slug: str | None = dict_get_recursive(chapter, "slug")
            chapter_id: int | None = dict_get_recursive(chapter, "id")

            if chapter_number is None or chapter_slug is None or chapter_id is None:
                continue

            chapters.append(
                MangaChapter(
                    "en",
                    self.display_name,
                    "chapter",
                    chapter_number,
                    None,
                    chapter_title
                    if chapter_title is not None and chapter_title != "" and chapter_title != chapter_number
                    else f"Chapter {chapter_number}",
                    f"{self._BASE_URL}/series/{slug_id}/{chapter_slug}",
                    str(chapter_id),
                )
            )

        return MangaDetail(title, [*alt_titles.split(" / ")], chapters)

    @override
    async def fetch_manga_pages(
        self, manga_id: str, manga_link: str, chapter_id: str, chapter_link: str
    ) -> list[MangaPage]:
        manga_pages = []
        pages: ChapterResponse = await self.get_json("/api/chapter", params={"chapterId": chapter_id})

        for page in dict_get_recursive(pages, "chapter", "images", default=[]):
            order: int | None = dict_get_recursive(page, "order")
            url: str | None = dict_get_recursive(page, "url")

            if order is None or url is None:
                continue

            manga_pages.append(MangaPage(order, url, None))

        return manga_pages