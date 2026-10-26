import json
import mimetypes
import re
from collections.abc import AsyncIterable, Sequence
from types import TracebackType
from typing import Self, cast, override

from aiohttp import ClientResponseError
from bs4 import BeautifulSoup
from bs4.element import Tag
from playwright.async_api import Browser, Page

from mangadotnet_scraper.camoufox_utils import create_browser
from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.base import (
    BaseModule,
    MangaChapter,
    MangaDetail,
    MangaImage,
    MangaListing,
    MangaPage,
)
from mangadotnet_scraper.modules.error import FetchError, SeriesNotFoundError
from mangadotnet_scraper.modules.manager import ModuleManager
from mangadotnet_scraper.utilities import (
    clean_string,
    dict_get_recursive,
)


class SpringToonsModule(BaseModule):
    _GROUP_ID = "Spring Toons"

    _browser: Browser
    _page: Page

    def __init__(self, config: MangaDotNetScraperConfig):
        super().__init__(
            config,
            module_id="spring_toons",
            display_name="Spring Toons",
            language="en",
            version=1,
            base_url="https://springtoons.org",
        )

    async def __aenter__(self) -> Self:
        self._browser = cast(Browser, await create_browser().__aenter__())
        self._page = await self._browser.new_page()
        await self._page.goto("about:blank")
        return await super().__aenter__()

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        try:
            if self._browser:
                await self._browser.close()
        finally:
            await super().__aexit__(_exc_type, _exc_value, _traceback)

    @override
    async def on_fetch_manga_listing(self) -> AsyncIterable[MangaListing]:
        async def fetch_listing_html(page: int = 1) -> str:
            return await self.get_html(
                "/explore",
                params={"type": ["manga", "manhwa", "manhua"], "page": page},
            )

        page = 1
        has_next_page = True

        while has_next_page:
            html = await fetch_listing_html(page)
            soup = BeautifulSoup(html, "html.parser")

            def search_script(tag: Tag) -> bool:
                return (
                    tag.name == "script"
                    and tag.find_parent(
                        "div", attrs={"style": "display: contents"}
                    )
                    is not None
                )

            script = soup.find(search_script)

            if script is None:
                raise FetchError("Unable to find script data")

            series = re.search(r"comics:(\[{.+?}\]),", script.text)

            if series is None:
                raise FetchError("Unable to find script data")

            series_json_str = await self._page.evaluate(f"""() => {{
                var test = {series[1]};
                return JSON.stringify(test);
            }}""")

            series_json = json.loads(series_json_str)

            for series in series_json:
                series_id = dict_get_recursive(series, "id")
                title = dict_get_recursive(series, "title")
                slug = dict_get_recursive(series, "slug")

                if series_id is None or title is None or slug is None:
                    continue

                yield MangaListing(
                    clean_string(series_id),
                    clean_string(title),
                    f"{self.base_url}/series/{slug}",
                )

            page += 1
            has_next_page = soup.find("a", attrs={"rel": "next"}) is not None

    @override
    async def on_fetch_manga_detail(
        self, manga_id: str, link: str
    ) -> MangaDetail:
        try:
            html = await self.get_html(link)
        except ClientResponseError as error:
            if error.code == 404:
                raise SeriesNotFoundError() from error
            else:
                raise

        soup = BeautifulSoup(html, "html.parser")

        title_element = soup.find("h1")
        title: str = (
            clean_string(title_element.get_text()) if title_element else ""
        )

        def search_alt_titles(tag: Tag) -> bool:
            return (
                tag.name == "p"
                and tag.find_parent(
                    "div", attrs={"class": "series-alternative-titles"}
                )
                is not None
            )

        alt_titles_element = soup.find(search_alt_titles)
        alt_titles = (
            alt_titles_element.text.split(" · ")
            if alt_titles_element is not None
            else []
        )

        def search_script(tag: Tag) -> bool:
            return (
                tag.name == "script"
                and tag.find_parent(
                    "div", attrs={"style": "display: contents"}
                )
                is not None
            )

        script = soup.find(search_script)

        if script is None:
            raise FetchError("Unable to find script data")

        chapters = []
        chapter_data = re.search(r"chapters:(\[.*?\]),", script.text)

        if chapter_data is not None:
            chapter_json_str = await self._page.evaluate(f"""() => {{
                var test = {chapter_data[1]};
                return JSON.stringify(test);
            }}""")

            chapter_json = json.loads(chapter_json_str)

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
                    MangaChapter(
                        self.language,
                        self._GROUP_ID,
                        "chapter",
                        number,
                        None,
                        chapter_title,
                        f"{self.base_url}/series-read/{slug}",
                        id,
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
        html = await self.get_html(chapter_link)
        soup = BeautifulSoup(html, "html.parser")

        def search_script(tag: Tag) -> bool:
            return (
                tag.name == "script"
                and tag.find_parent(
                    "div", attrs={"style": "display: contents"}
                )
                is not None
            )

        script = soup.find(search_script)

        if script is None:
            raise FetchError("Unable to find script data")

        pages = []
        page_data = re.search(r"pages:(\[.*?\]),", script.text)

        if page_data is not None:
            page_json_str = await self._page.evaluate(f"""() => {{
                var test = {page_data[1]};
                return JSON.stringify(test);
            }}""")

            page_json = json.loads(page_json_str)

            for page in page_json:
                index = dict_get_recursive(page, "index")
                url = dict_get_recursive(page, "url")

                if index is None or url is None:
                    continue

                pages.append(MangaPage(index, url))

        return pages

    @override
    async def on_fetch_manga_image(self, page: MangaPage) -> MangaImage:
        content_type, data = await self.download_image(
            page.image_link, headers={"Referer": f"{self.base_url}/"}
        )
        filename = f"{page.page_number:03d}{mimetypes.guess_extension(content_type, False)}"
        return MangaImage(filename, data)


ModuleManager.register_module(SpringToonsModule)
