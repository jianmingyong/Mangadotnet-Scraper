from collections.abc import AsyncIterable, Sequence
from typing import ReadOnly, TypedDict, override

from mangadotnet_scraper.modules.base import (
    BaseModule,
    MangaChapter,
    MangaDetail,
    MangaListing,
    MangaPage,
)
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


class IkenTemplate(BaseModule):
    @override
    async def on_fetch_manga_listing(self) -> AsyncIterable[MangaListing]:
        async def fetch_listing(page: int = 1) -> PostsResponse:
            return await self.get_json(
                "/api/posts",
                params={
                    "page": page,
                    "perPage": 100,
                    "isNovel": "false",
                    "tag": "new",
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

                yield MangaListing(
                    str(id),
                    clean_string(title),
                    f"{self.base_url}/series/{clean_string(slug)}",
                )

            has_next_page = page * 100 < dict_get_recursive(
                json, "totalCount", default=0
            )
            page += 1

    @override
    async def on_fetch_manga_detail(
        self, manga_id: str, link: str
    ) -> MangaDetail:
        json: PostResponse = await self.get_json(
            "/api/post", params={"postId": manga_id}
        )

        title = dict_get_recursive(json, "post", "postTitle", default="")
        alt_titles = dict_get_recursive(
            json, "post", "alternativeTitles", default=""
        ).splitlines()

        chapters = []
        chapters_json: ChaptersResponse = await self.get_json(
            "/api/chapters", params={"postId": manga_id}
        )

        for chapter in dict_get_recursive(
            chapters_json, "post", "chapters", default=[]
        ):
            if dict_get_recursive(chapter, "isLocked", default=False):
                continue

            chapter_title: str | None = dict_get_recursive(chapter, "title")
            number: float | None = dict_get_recursive(chapter, "number")
            chapter_slug: str | None = dict_get_recursive(chapter, "slug")
            chapter_id: int | None = dict_get_recursive(chapter, "id")

            if number is None or chapter_slug is None or chapter_id is None:
                continue

            if (
                chapter_title is None
                or chapter_title == ""
                or chapter_title == number
            ):
                chapter_title = f"Chapter {number:.1f}".rstrip("0").rstrip(".")

            chapters.append(
                MangaChapter(
                    "en",
                    self.display_name,
                    "chapter",
                    number,
                    None,
                    chapter_title,
                    f"{link}/{chapter_slug}",
                    str(chapter_id),
                )
            )

        return MangaDetail(title, alt_titles, chapters)

    @override
    async def on_fetch_manga_pages(
        self,
        manga_id: str,
        manga_link: str,
        chapter_id: str,
        chapter_link: str,
    ) -> Sequence[MangaPage]:
        manga_pages = []
        pages: ChapterResponse = await self.get_json(
            "/api/chapter", params={"chapterId": chapter_id}
        )

        for page in dict_get_recursive(pages, "chapter", "images", default=[]):
            order: int | None = dict_get_recursive(page, "order")
            url: str | None = dict_get_recursive(page, "url")

            if order is None or url is None:
                continue

            manga_pages.append(MangaPage(order, url, None))

        return manga_pages
