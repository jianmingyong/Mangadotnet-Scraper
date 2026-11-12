import re
from collections.abc import AsyncGenerator, Mapping, Sequence
from typing import Any, Final, Unpack, cast, override

from bs4 import BeautifulSoup, Tag

from mangadotnet_scraper.config import Config
from mangadotnet_scraper.network import HttpResponseError
from mangadotnet_scraper.sources.base import (
    BaseSourceProvider,
    Chapter,
    ImageRequest,
    Manga,
    Page,
    SourceInfo,
)
from mangadotnet_scraper.utilities import clean_chapter_title, normalize_url


class KeyoAppLivewireTemplate(BaseSourceProvider):
    group_name: Final[str]
    base_cdn_url: Final[str]

    def __init__(
        self,
        config: Config,
        group_name: str,
        base_cdn_url: str,
        **kwargs: Unpack[SourceInfo],
    ) -> None:
        super().__init__(config, **kwargs)

        self.group_name = group_name
        self.base_cdn_url = base_cdn_url

    async def fetch_listing_html(self, page: int = 1) -> str:
        return await self.client.get_text("/latest", params={"page": page})

    def is_chapter_link_element(self, tag: Tag) -> bool:
        return (
            tag.name == "a"
            and tag.has_attr("href")
            and re.search("/read/", cast(str, tag.get("href", default="")))
            is not None
            and tag.find_parent("div", attrs={"id": "chapters"}) is not None
        )

    async def test_page_response(self, link: str) -> bool:
        try:
            await self.client.head(link)
            return True
        except HttpResponseError as error:
            if error.status == 404:
                return False
            else:
                raise

    @override
    async def _on_get_manga_list(self) -> AsyncGenerator[Manga]:
        page = 1
        has_next_page = True

        while has_next_page:
            html = await self.fetch_listing_html(page)
            soup = BeautifulSoup(html, "html.parser")

            elements = soup.find_all(
                "a", {"href": re.compile("/series/"), "class": "grid"}
            )

            for element in elements:
                link = cast(str | None, element.get("href"))
                title = cast(str | None, element.get("title"))

                if title is None or link is None:
                    continue

                if link.endswith("/"):
                    series_id = link[: link.rfind("/")]
                    series_id = series_id[series_id.rfind("/") + 1 :]
                else:
                    series_id = link[link.rfind("/") + 1 :]

                yield Manga(id=series_id, title=title, link=link)

            page += 1
            has_next_page = (
                soup.find("a", attrs={"wire:click.prevent": "loadMore"})
                is not None
            )

    @override
    async def _on_get_manga_update(
        self,
        manga: Manga,
        need_details: bool = True,
        need_chapters: bool = True,
    ) -> Manga:
        new_manga = manga.copy()

        html = await self.client.get_text(manga.link)
        soup = BeautifulSoup(html, "html.parser")

        if need_details:
            title_element = soup.find("h1")
            new_manga.title = (
                title_element.get_text(strip=True)
                if title_element
                else new_manga.title
            )

            alt_titles_element = soup.find_all(
                "li", attrs={"class": "select-all"}
            )
            new_manga.alt_titles = (
                [e.get_text(strip=True) for e in alt_titles_element]
                if alt_titles_element
                else new_manga.alt_titles
            )

        if need_chapters:
            chapters = []
            chapter_elements = soup.find_all(self.is_chapter_link_element)

            for chapter_element in chapter_elements:
                chapter_title = cast(str | None, chapter_element.get("title"))

                if chapter_title is None:
                    continue

                title_match = re.search(
                    "Chapter (\\d+\\.\\d+|\\d+)", chapter_title
                )

                if title_match is None:
                    continue
                else:
                    chapter_number = float(title_match[1])

                chapter_link = cast(str | None, chapter_element.get("href"))

                if chapter_link is None:
                    continue

                chapters.append(
                    Chapter(
                        id=chapter_link[chapter_link.rfind("/") + 1 :],
                        language="en",
                        group=self.group_name,
                        type="chapter",
                        volume_number=None,
                        chapter_number=chapter_number,
                        title=clean_chapter_title(chapter_number),
                        link=chapter_link,
                    )
                )

            new_manga.chapters = chapters

        return new_manga

    @override
    async def _on_get_page_list(
        self, manga: Manga, chapter: Chapter
    ) -> Sequence[Page]:
        html = await self.client.get_text(chapter.link)
        soup = BeautifulSoup(html, "html.parser")

        pages = []

        x_data_element = soup.find(
            "div", attrs={"x-data": re.compile("^immersiveReader")}
        )

        if x_data_element is None:
            return pages

        x_data = cast(str, x_data_element.get("x-data", default="{}"))

        browser = await self.get_browser()

        async with await browser.new_page() as page:
            x_data_json: Mapping[str, Any] = await page.evaluate(
                f"""
                (() => {{
                    let immersiveReader = (params) => params;
                    return {x_data};
                }})()
                """
            )

            image_base_url = x_data_json.get("baseLink", self.base_cdn_url)

            if not isinstance(image_base_url, str):
                return pages

            image_pages = x_data_json.get("pages", [])

            if not isinstance(image_pages, Sequence):
                return pages

            if len(image_pages) == 0:
                # This is a premium chapter, we can't actually get the data here so we might as well guess?
                page = 1

                revision_element = soup.find("meta", {"property": "og:image"})

                if revision_element is None:
                    return pages

                revision_id = cast(str | None, revision_element.get("content"))

                if (
                    revision_id is not None
                    and "/revisions/" not in revision_id
                ):
                    revision_id = None

                if revision_id is not None:
                    revision_id = revision_id[: revision_id.rfind("/")]
                    revision_id = revision_id[revision_id.rfind("/") + 1 :]

                while True:
                    if revision_id is None:
                        image_link = f"{self.base_cdn_url}/series/webtoon/{manga.id}/chapters/{chapter.id}/{page:03d}.jpg"
                    else:
                        image_link = f"{self.base_cdn_url}/series/webtoon/{manga.id}/chapters/{chapter.id}/revisions/{revision_id}/{page:03d}.jpg"

                    if await self.test_page_response(image_link):
                        pages.append(Page(page, image_link))
                        page += 1
                    else:
                        break
            else:
                # Free Chapter
                for idx, image in enumerate(image_pages):
                    if isinstance(image, Mapping):
                        pages.append(
                            Page(
                                idx,
                                normalize_url(
                                    image.get("path", ""), image_base_url
                                ),
                            )
                        )

        return pages

    @override
    async def _on_get_image_request(self, page: Page) -> ImageRequest:
        return ImageRequest(headers={"Referer": f"{self.base_url}/"})
