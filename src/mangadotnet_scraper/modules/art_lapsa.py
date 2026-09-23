import json
import re
from collections.abc import AsyncIterable
from typing import cast, override

from bs4 import BeautifulSoup, Tag
from playwright.async_api import Browser, Error

from mangadotnet_scraper.camoufox_utils import create_browser
from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.base import BaseModule, MangaChapter, MangaDetail, MangaListing, MangaPage
from mangadotnet_scraper.network import retryable_client_session
from mangadotnet_scraper.utilities import clean_string, dict_get_recursive


class ArtLapsaModule(BaseModule):
    _BASE_URL = "https://artlapsa.com"
    _BASE_CDN_URL = "https://cdn.artlapsa.com"

    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        super().__init__(config, "art_lapsa", "Art Lapsa", self._BASE_URL)

    @override
    async def fetch_manga_listing(self) -> AsyncIterable[MangaListing]:
        async with create_browser() as browser, await cast(Browser, browser).new_context() as context:
            page = await context.new_page()
            await page.goto(f"{self._BASE_URL}/latest", wait_until="domcontentloaded")

            while True:
                try:
                    button = await page.wait_for_selector('button[wire\\:click="loadMore"]', state="attached")

                    if button is not None:
                        await button.click()
                    else:
                        break
                except Error:
                    break

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            elements = soup.find_all("a", {"href": re.compile("/series/"), "class": "grid"})

            for element in elements:
                link = cast(str, element.attrs.get("href"))
                title = cast(str, element.attrs.get("title"))
                series_id = link[link.rfind("/") + 1 :]

                if title is None or link is None:
                    continue

                yield MangaListing(clean_string(series_id), clean_string(title), clean_string(link))

    @override
    async def fetch_manga_detail(self, manga_id: str, link: str) -> MangaDetail:
        html = await self.get_html(link)
        soup = BeautifulSoup(html, "html.parser")

        title_element = soup.find("h1")
        title = clean_string(title_element.text) if title_element else ""

        alt_titles_element = soup.find_all("span", attrs={"class": "select-all"})
        alt_titles = [clean_string(e.text) for e in alt_titles_element]

        def is_chapter_link_element(tag: Tag) -> bool:
            return (
                tag.name == "a"
                and tag.has_attr("href")
                and re.compile("/read/").search(str(tag.attrs["href"])) is not None
                and tag.find_parent("div", attrs={"id": "chapters"}) is not None
            )

        chapter_elements = soup.find_all(is_chapter_link_element)
        chapters = []

        for chapter_element in chapter_elements:
            chapter_title = chapter_element.attrs.get("title")
            if not chapter_title or not isinstance(chapter_title, str):
                continue

            title_match = re.compile("Chapter (\\d+|\\d+\\.\\d+)").search(chapter_title)

            if title_match:
                chapter_number = float(title_match[1])
            else:
                continue

            chapter_link = cast(str, chapter_element.attrs.get("href"))

            if chapter_link is None:
                continue

            chapters.append(
                MangaChapter(
                    "en",
                    self.display_name,
                    "chapter",
                    chapter_number,
                    None,
                    f"Chapter {chapter_number:.1f}".rstrip("0").rstrip("."),
                    f"{self._BASE_URL}{chapter_link}",
                    chapter_link[chapter_link.rfind("/") + 1 :],
                )
            )

        return MangaDetail(title, alt_titles, chapters)

    @override
    async def fetch_manga_pages(
        self, manga_id: str, manga_link: str, chapter_id: str, chapter_link: str
    ) -> list[MangaPage]:
        html = await self.get_html(chapter_link)
        soup = BeautifulSoup(html, "html.parser")

        json_element = soup.find("div", attrs={"x-data": re.compile("^immersiveReader")})

        if json_element is None:
            return []

        pages: list[MangaPage] = []

        json_str = str(json_element.attrs.get("x-data")).strip()
        match = re.search(r"pages\s*:\s*JSON\.parse\s*\(\s*(['\"])(.*?)\1\s*\)", json_str, re.DOTALL)

        if match is None:
            # This is a premium chapter, we can't actually get the data here so we might as well guess?
            series_id = manga_link[manga_link.rfind("/") + 1 :]
            chapter_id = chapter_link[chapter_link.rfind("/") + 1 :]
            page = 1

            revision_element = soup.find("script", attrs={"type": "application/ld+json"})

            if revision_element is None:
                return []

            try:
                revision_json = json.loads(revision_element.text)
            except json.decoder.JSONDecodeError:
                return []

            revision_id: str | None = dict_get_recursive(revision_json, "image", "url")

            if revision_id is not None:
                revision_id = revision_id[: revision_id.rfind("/")]
                revision_id = revision_id[revision_id.rfind("/") + 1 :]

            @retryable_client_session
            async def test_page_response(page_number: int, link: str) -> bool:
                async with self.session.head(link) as test_response:
                    if test_response.ok:
                        pages.append(MangaPage(page_number, link, {}))
                        return True
                    else:
                        return False

            while True:
                if await test_page_response(
                    page,
                    f"{self._BASE_CDN_URL}/series/webtoon/{series_id}/chapters/{chapter_id}/{page:03d}.jpg"
                    if revision_id is None
                    else f"{self._BASE_CDN_URL}/series/webtoon/{series_id}/chapters/{chapter_id}/revisions/{revision_id}/{page:03d}.jpg",
                ):
                    page += 1
                else:
                    break
        else:
            encoded = match.group(2)
            decoded = bytes(encoded, "utf-8").decode("unicode_escape")

            try:
                json_obj = json.loads(decoded)
            except json.decoder.JSONDecodeError:
                return []

            if isinstance(json_obj, list):
                json_pages = json_obj

                for i, page in zip(range(len(json_pages)), json_pages):
                    if isinstance(page, dict):
                        pages.append(
                            MangaPage(
                                i,
                                f"{cast(str, page.get('path', '')).replace('\\', '')}",
                                {
                                    "width": page.get("width"),
                                    "height": page.get("height"),
                                    "format": page.get("format"),
                                    "size": page.get("size"),
                                },
                            )
                        )

        return pages
