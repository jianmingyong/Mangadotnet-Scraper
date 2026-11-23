from collections.abc import AsyncGenerator, Sequence
from typing import ReadOnly, TypedDict, override

from mangadotnet_scraper.sources import (
    BaseSourceProvider,
    Chapter,
    ImageRequest,
    Manga,
    Page,
    SourceProvider,
)
from mangadotnet_scraper.utilities import (
    clean_alt_titles,
    clean_chapter_title,
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


class RenaScansSourceProvider(BaseSourceProvider):
    GROUP_NAME = "Renascans"

    def __init__(self, **kwargs) -> None:
        super().__init__(
            source_id="en.rena_scans",
            name="Rena Scans",
            version=1,
            languages=["en"],
            base_url="https://renascans.net",
            **kwargs,
        )

    @override
    async def _on_initialize(self) -> None:
        if self.user_agent is None:
            self.user_agent = self.browser.user_agent

    @override
    async def _on_get_manga_list(self) -> AsyncGenerator[Manga]:
        offset = 0
        has_next_page = True

        while has_next_page:
            json: MangaListResponse = await self.get_json(
                "/api/v1/manga",
                params={
                    "offset": offset,
                    "limit": 100,
                    "sort": "newest",
                },
            )

            if not isinstance(json, Sequence):
                break

            for post in json:
                id: int | None = dict_get_recursive(post, "id")
                title: str | None = dict_get_recursive(post, "title")
                slug: str | None = dict_get_recursive(post, "slug")

                if id is None or title is None or slug is None:
                    continue

                yield Manga(
                    str(id),
                    clean_string(title),
                    f"{self.base_url}/manga/{slug}",
                )

            has_next_page = len(json) == 100
            offset += 100

    @override
    async def _on_get_manga_update(
        self,
        manga: Manga,
        need_details: bool = True,
        need_chapters: bool = True,
    ) -> Manga:
        new_manga = manga.copy()

        slug = manga.link[manga.link.rindex("/") + 1 :]
        json: MangaResponse = await self.get_json(f"/api/v1/manga/{slug}")

        if need_details:
            new_manga.title = dict_get_recursive(
                json, "title", default=new_manga.title
            )
            new_manga.alt_titles = clean_alt_titles(
                dict_get_recursive(json, "alt_titles")
            )

        if need_chapters:
            chapters = []

            for chapter in dict_get_recursive(json, "chapters", default=[]):
                if dict_get_recursive(chapter, "is_locked", default=False):
                    continue

                chapter_title: str | None = dict_get_recursive(
                    chapter, "title"
                )
                number: float | None = dict_get_recursive(
                    chapter, "chapter_number"
                )
                chapter_id: int | None = dict_get_recursive(chapter, "id")

                if number is None or chapter_id is None:
                    continue

                chapters.append(
                    Chapter(
                        id=str(chapter_id),
                        language="en",
                        group=self.GROUP_NAME,
                        type="chapter",
                        volume_number=None,
                        chapter_number=number,
                        title=clean_chapter_title(number, chapter_title),
                        link=f"{manga.link}/{clean_chapter_title(number, chapter_title).lower().replace(' ', '-')}",
                    )
                )

            new_manga.chapters = chapters

        return new_manga

    @override
    async def _on_get_page_list(
        self, manga: Manga, chapter: Chapter
    ) -> Sequence[Page]:
        manga_pages = []

        json: MangaPageResponse = await self.get_json(
            f"/api/v1/chapters/{chapter.id}"
        )

        for index, image in enumerate(
            dict_get_recursive(json, "content", default=[])
        ):
            manga_pages.append(
                Page(page=index, link=f"https://renascans.net/uploads/{image}")
            )

        return manga_pages

    @override
    def _on_get_image_request(self, page: Page) -> ImageRequest:
        return ImageRequest(
            url=page.link, headers={"Referer": f"{self.base_url}/"}
        )


SourceProvider.register_source(RenaScansSourceProvider)
