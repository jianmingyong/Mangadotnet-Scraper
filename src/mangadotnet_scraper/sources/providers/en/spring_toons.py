import re
from collections.abc import AsyncGenerator, Sequence
from typing import override

from bs4 import BeautifulSoup, Tag

from mangadotnet_scraper.config import Config
from mangadotnet_scraper.sources import BaseSourceProvider, SourceProvider
from mangadotnet_scraper.sources.base import (
    Chapter,
    ImageRequest,
    Manga,
    Page,
    SourceError,
)
from mangadotnet_scraper.utilities import dict_get_recursive


class SpringToonsSourceProvider(BaseSourceProvider):
    GROUP_ID = "Spring Toons"

    def __init__(self, config: Config) -> None:
        super().__init__(
            config,
            source_id="en.spring_toons",
            name="Spring Toons",
            version=1,
            languages=["en"],
            base_url="https://springtoons.org",
        )

    async def fetch_listing_html(self, page: int = 1) -> str:
        return await self.client.get_text(
            "/explore",
            params={"type": ["manga", "manhwa", "manhua"], "page": page},
        )

    def search_script(self, tag: Tag) -> bool:
        return (
            tag.name == "script"
            and tag.find_parent("div", attrs={"style": "display: contents"})
            is not None
        )

    def search_alt_titles(self, tag: Tag) -> bool:
        return (
            tag.name == "p"
            and tag.find_parent(
                "div", attrs={"class": "series-alternative-titles"}
            )
            is not None
        )

    @override
    async def _on_get_manga_list(self) -> AsyncGenerator[Manga]:
        page = 1
        has_next_page = True

        while has_next_page:
            html = await self.fetch_listing_html(page)
            soup = BeautifulSoup(html, "html.parser")

            script = soup.find(self.search_script)

            if script is None:
                raise SourceError("Unable to find script data")

            series = re.search(r"comics:(\[{.+?}\]),", script.text)

            if series is None:
                raise SourceError("Unable to find script data")

            browser = await self.get_browser()

            async with await browser.new_page() as browser_page:
                series_json = await browser_page.evaluate(f"() => {series[1]}")

                for series in series_json:
                    series_id = dict_get_recursive(series, "id")
                    title = dict_get_recursive(series, "title")
                    slug = dict_get_recursive(series, "slug")

                    if series_id is None or title is None or slug is None:
                        continue

                    yield Manga(
                        series_id,
                        title,
                        f"{self.base_url}/series/{slug}",
                    )

            page += 1
            has_next_page = soup.find("a", attrs={"rel": "next"}) is not None

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

        script = soup.find(self.search_script)

        if script is None:
            raise SourceError("Unable to find script data")

        if need_details:
            title_element = soup.find("h1")
            new_manga.title = (
                title_element.get_text(strip=True)
                if title_element
                else new_manga.title
            )

            alt_titles_data = re.search(
                r"alternativeTitles:(\[.*?\]),", script.text
            )

            if alt_titles_data is not None:
                browser = await self.get_browser()

                async with await browser.new_page() as browser_page:
                    alt_titles_json = await browser_page.evaluate(
                        f"() => {alt_titles_data[1]}"
                    )

                    new_manga.alt_titles = (
                        alt_titles_json
                        if alt_titles_json
                        else new_manga.alt_titles
                    )

        if need_chapters:
            chapters = []
            chapter_data = re.search(r"chapters:(\[.*?\]),", script.text)

            if chapter_data is not None:
                browser = await self.get_browser()

                async with await browser.new_page() as browser_page:
                    chapter_json = await browser_page.evaluate(
                        f"() => {chapter_data[1]}"
                    )

                    for chapter in chapter_json:
                        is_premium = dict_get_recursive(
                            chapter, "isPremium", default=False
                        )

                        if is_premium:
                            continue

                        number = dict_get_recursive(chapter, "number")
                        chapter_title = dict_get_recursive(chapter, "title")
                        id = dict_get_recursive(chapter, "id")
                        slug = dict_get_recursive(chapter, "slug")

                        if (
                            number is None
                            or chapter_title is None
                            or id is None
                            or slug is None
                        ):
                            continue

                        chapters.append(
                            Chapter(
                                id=id,
                                language="en",
                                group=self.GROUP_ID,
                                type="chapter",
                                volume_number=None,
                                chapter_number=number,
                                title=chapter_title,
                                link=f"{self.base_url}/series-read/{slug}",
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

        script = soup.find(self.search_script)

        if script is None:
            raise SourceError("Unable to find script data")

        pages = []
        page_data = re.search(r"pages:(\[.*?\]),", script.text)

        if page_data is not None:
            browser = await self.get_browser()

            async with await browser.new_page() as browser_page:
                page_json = await browser_page.evaluate(
                    f"() => {page_data[1]}"
                )

                for page in page_json:
                    index = dict_get_recursive(page, "index")
                    url = dict_get_recursive(page, "url")

                    if index is None or url is None:
                        continue

                    pages.append(Page(index, url))

        return pages

    @override
    async def _on_get_image_request(self, page: Page) -> ImageRequest:
        return ImageRequest(headers={"Referer": f"{self.base_url}/"})


SourceProvider.register_source(SpringToonsSourceProvider)
