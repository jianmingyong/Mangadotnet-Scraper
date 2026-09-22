from collections.abc import AsyncIterable, Collection
from typing import TypedDict, override

from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.base import BaseModule, MangaChapter, MangaDetail, MangaListing, MangaPage
from mangadotnet_scraper.utilities import clean_string, safe_dict_get


class NyxScansModule(BaseModule):
    _BASE_URL = "https://nyxscans.com"
    _BASE_API_URL = "https://api.nyxscans.com"

    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        super().__init__(config, "nyx_scans", "Nyx Scans", self._BASE_URL, self._BASE_API_URL)

    @override
    async def initialize(self) -> None:
        await super().initialize()
        self.fetch_concurrency = 2

    class PostsResponse(TypedDict):
        posts: Collection[NyxScansModule.PostsResponsePost]
        totalCount: int

    class PostsResponsePost(TypedDict):
        id: int
        slug: str
        postTitle: str

    @override
    async def fetch_manga_listing(self) -> AsyncIterable[MangaListing]:
        async def fetch_listing(page: int = 1) -> self.PostsResponse:
            return await self.get_json(
                "/api/posts", params={"page": page, "perPage": 100, "isNovel": "false", "tag": "new"}
            )

        page = 1
        has_next_page = True

        while has_next_page:
            json = await fetch_listing(page)

            for post in safe_dict_get(json, "posts", type=Collection[self.PostsResponsePost], default=[]):
                id = safe_dict_get(post, "id", type=int)
                title = safe_dict_get(post, "postTitle", type=str)
                slug = safe_dict_get(post, "slug", type=str)

                if id is None or title is None or slug is None:
                    continue

                yield MangaListing(str(id), clean_string(title), f"{self._BASE_URL}/series/{clean_string(slug)}")

            has_next_page = page * 100 < safe_dict_get(json, "totalCount", type=int, default=0)
            page += 1

    class PostResponse(TypedDict):
        post: NyxScansModule.PostResponsePost

    class PostResponsePost(TypedDict):
        postTitle: str
        alternativeTitles: str

    class ChaptersResponse(TypedDict):
        post: NyxScansModule.ChaptersResponsePost

    class ChaptersResponsePost(TypedDict):
        chapters: Collection[NyxScansModule.ChaptersResponsePostChapter]

    class ChaptersResponsePostChapter(TypedDict):
        id: int
        slug: str
        number: float
        title: str
        isLocked: bool

    @override
    async def fetch_manga_detail(self, manga_id: str, link: str) -> MangaDetail:
        slug = link[link.rfind("/") + 1 :]
        json: self.PostResponse = await self.get_json("/api/post", params={"postId": manga_id})

        title = safe_dict_get(json, "post", "postTitle", type=str, default="")
        alt_titles = safe_dict_get(json, "post", "alternativeTitles", type=str, default="").splitlines()

        chapters = []
        chapters_json: self.ChaptersResponse = await self.get_json("/api/chapters", params={"postId": manga_id})

        for chapter in safe_dict_get(
            chapters_json, "post", "chapters", type=Collection[self.ChaptersResponsePostChapter], default=[]
        ):
            if safe_dict_get(chapter, "isLocked", type=bool, default=False):
                continue

            chapter_title = safe_dict_get(chapter, "title", type=str)
            number = safe_dict_get(chapter, "number", type=float)
            chapter_slug = safe_dict_get(chapter, "slug", type=str)
            chapter_id = safe_dict_get(chapter, "id", type=int)

            if number is None or chapter_slug is None or chapter_id is None:
                continue

            if chapter_title is None or chapter_title == "" or chapter_title == number:
                chapter_title = f"Chapter {number:.1f}".rstrip("0").rstrip(".")

            chapters.append(
                MangaChapter(
                    "en",
                    self.display_name,
                    "chapter",
                    number,
                    None,
                    chapter_title,
                    f"{self._BASE_URL}/{slug}/{chapter_slug}",
                    str(chapter_id),
                )
            )

        return MangaDetail(title, alt_titles, chapters)

    class ChapterResponse(TypedDict):
        chapter: NyxScansModule.ChapterResponseObject

    class ChapterResponseObject(TypedDict):
        images: Collection[NyxScansModule.ChapterResponseObjectImages]

    class ChapterResponseObjectImages(TypedDict):
        id: int
        url: str
        width: int
        height: int
        order: int

    @override
    async def fetch_manga_pages(
        self, manga_id: str, manga_link: str, chapter_id: str, chapter_link: str
    ) -> list[MangaPage]:
        manga_pages = []
        pages: self.ChapterResponse = await self.get_json("/api/chapter", params={"chapterId": chapter_id})

        for page in safe_dict_get(
            pages, "chapter", "images", type=Collection[self.ChapterResponseObjectImages], default=[]
        ):
            order = safe_dict_get(page, "order", type=int)
            url = safe_dict_get(page, "url", type=str)

            if order is None or url is None:
                continue

            manga_pages.append(MangaPage(order, url, None))

        return manga_pages
