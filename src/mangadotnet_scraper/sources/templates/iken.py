from collections.abc import AsyncGenerator, Sequence
from typing import Final, ReadOnly, TypedDict, Unpack, override

from mangadotnet_scraper.config import Config
from mangadotnet_scraper.network import HttpClient
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
    alternativeTitles: ReadOnly[str | None]


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


class IkenTemplate(BaseSourceProvider):
    group_name: Final[str]
    base_api_url: Final[str | None]

    def __init__(
        self,
        config: Config,
        group_name: str,
        base_api_url: str | None = None,
        **kwargs: Unpack[SourceInfo],
    ) -> None:
        super().__init__(config, **kwargs)

        self.group_name = group_name
        self.base_api_url = base_api_url

    @override
    async def initialize(self) -> None:
        await super().initialize()

        if self.base_api_url is not None:
            if self.client is not None:
                await self.client.close()

            self.client = HttpClient(
                self.base_api_url,
                headers={
                    "Origin": self.base_url,
                    "Referer": f"{self.base_url}/",
                },
            )

    async def fetch_listing(self, page: int = 1) -> PostsResponse:
        return await self.client.get_json(
            "/api/posts",
            params={
                "page": page,
                "perPage": 100,
                "isNovel": "false",
            },
        )

    @override
    async def _on_get_manga_list(self) -> AsyncGenerator[Manga]:
        page = 1
        has_next_page = True

        while has_next_page:
            json = await self.fetch_listing(page)

            for post in dict_get_recursive(json, "posts", default=[]):
                id: int | None = dict_get_recursive(post, "id")
                title: str | None = dict_get_recursive(post, "postTitle")
                slug: str | None = dict_get_recursive(post, "slug")

                if id is None or title is None or slug is None:
                    continue

                yield Manga(
                    id=str(id),
                    title=title,
                    link=f"{self.base_url}/series/{slug}",
                )

            has_next_page = page * 100 < dict_get_recursive(
                json, "totalCount", default=0
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

        if need_details:
            json: PostResponse = await self.client.get_json(
                "/api/post", params={"postId": manga.id}
            )

            new_manga.title = dict_get_recursive(
                json, "post", "postTitle", default=new_manga.title
            )

            alt_titles_str: str | None = dict_get_recursive(
                json, "post", "alternativeTitles"
            )

            new_manga.alt_titles = (
                clean_alt_titles(alt_titles_str)
                if alt_titles_str is not None
                else new_manga.alt_titles
            )

        if need_chapters:
            chapters = []
            chapters_json: ChaptersResponse = await self.client.get_json(
                "/api/chapters", params={"postId": manga.id}
            )

            for chapter in dict_get_recursive(
                chapters_json, "post", "chapters", default=[]
            ):
                if dict_get_recursive(chapter, "isLocked", default=False):
                    continue

                chapter_title: str | None = dict_get_recursive(
                    chapter, "title"
                )
                number: float | None = dict_get_recursive(chapter, "number")
                chapter_slug: str | None = dict_get_recursive(chapter, "slug")
                chapter_id: int | None = dict_get_recursive(chapter, "id")

                if (
                    number is None
                    or chapter_slug is None
                    or chapter_id is None
                ):
                    continue

                chapters.append(
                    Chapter(
                        id=str(chapter_id),
                        language="en",
                        group=self.group_name,
                        type="chapter",
                        volume_number=None,
                        chapter_number=number,
                        title=clean_chapter_title(number, chapter_title),
                        link=f"{manga.link}/{chapter_slug}",
                    )
                )

            new_manga.chapters = chapters

        return new_manga

    @override
    async def _on_get_page_list(
        self, manga: Manga, chapter: Chapter
    ) -> Sequence[Page]:
        manga_pages = []
        pages: ChapterResponse = await self.client.get_json(
            "/api/chapter", params={"chapterId": chapter.id}
        )

        for page in dict_get_recursive(pages, "chapter", "images", default=[]):
            order: int | None = dict_get_recursive(page, "order")
            url: str | None = dict_get_recursive(page, "url")

            if order is None or url is None:
                continue

            manga_pages.append(Page(order, url))

        return manga_pages

    @override
    async def _on_get_image_request(self, page: Page) -> ImageRequest:
        return ImageRequest(headers={"Referer": f"{self.base_url}/"})
