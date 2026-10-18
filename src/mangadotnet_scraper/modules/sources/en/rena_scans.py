from collections.abc import AsyncIterable, Sequence
from typing import ReadOnly, TypedDict, override

from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules import BaseModule
from mangadotnet_scraper.modules.base import (
    MangaChapter,
    MangaDetail,
    MangaListing,
    MangaPage,
)
from mangadotnet_scraper.utilities import (
    clean_alt_titles,
    clean_string,
    dict_get_recursive,
)


class MangaListResponse(TypedDict):
    id: ReadOnly[int]
    title: ReadOnly[str]
    slug: ReadOnly[str]


class MangaResponse(TypedDict):
    id: ReadOnly[int]
    title: ReadOnly[str]
    slug: ReadOnly[str]
    alt_titles: ReadOnly[str]
    chapters: ReadOnly[Sequence[MangaResponseChapter]]


class MangaResponseChapter(TypedDict):
    id: ReadOnly[int]
    title: ReadOnly[str]
    chapter_number: ReadOnly[float]
    is_locked: ReadOnly[bool]


class MangaPageResponse(TypedDict):
    content: ReadOnly[Sequence[str]]


class RenaScansModule(BaseModule):
    _GROUP_NAME = "Renascans"

    def __init__(self, config: MangaDotNetScraperConfig):
        super().__init__(
            config,
            module_id="rena_scans",
            display_name="Rena Scans",
            language="en",
            version=2,
            base_url="https://renascans.net",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:158.0) Gecko/20100101 Firefox/158.0",
        )

    async def on_fetch_manga_listing(self) -> AsyncIterable[MangaListing]:
        async def fetch_listing(
            offset: int = 0,
        ) -> Sequence[MangaListResponse]:
            return await self.get_json(
                "/api/v1/manga",
                params={
                    "offset": offset,
                    "limit": 100,
                    "sort": "newest",
                },
            )

        offset = 0
        has_next_page = True

        while has_next_page:
            json = await fetch_listing(offset)

            if not isinstance(json, Sequence):
                break

            for post in json:
                id: int | None = dict_get_recursive(post, "id")
                title: str | None = dict_get_recursive(post, "title")
                slug: str | None = dict_get_recursive(post, "slug")

                if id is None or title is None or slug is None:
                    continue

                yield MangaListing(
                    str(id),
                    clean_string(title),
                    f"{self.base_url}/manga/{slug}",
                )

            has_next_page = len(json) == 100
            offset += 100

    @override
    async def on_fetch_manga_detail(
        self, manga_id: str, link: str
    ) -> MangaDetail:
        slug = link[link.rindex("/") + 1 :]
        json: MangaResponse = await self.get_json(f"/api/v1/manga/{slug}")

        title = clean_string(dict_get_recursive(json, "title", default=""))
        alt_titles = clean_alt_titles(dict_get_recursive(json, "alt_titles"))

        chapters = []

        for chapter in dict_get_recursive(json, "chapters", default=[]):
            if dict_get_recursive(chapter, "is_locked", default=False):
                continue

            chapter_title: str | None = dict_get_recursive(chapter, "title")
            number: float | None = dict_get_recursive(
                chapter, "chapter_number"
            )
            chapter_id: int | None = dict_get_recursive(chapter, "id")

            if number is None or chapter_id is None:
                continue

            if (
                chapter_title is None
                or chapter_title == ""
                or chapter_title == number
            ):
                chapter_title = f"Chapter {number:.1f}".rstrip("0").rstrip(".")

            chapters.append(
                MangaChapter(
                    self.language,
                    self._GROUP_NAME,
                    "chapter",
                    number,
                    None,
                    chapter_title,
                    f"{link}/{chapter_title.lower().replace(' ', '-')}",
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
        manga_pages: list[MangaPage] = []

        json: MangaPageResponse = await self.get_json(
            f"/api/v1/chapters/{chapter_id}"
        )

        for index, image in enumerate(
            dict_get_recursive(json, "content", default=[])
        ):
            manga_pages.append(MangaPage(index, image, None))

        return manga_pages
