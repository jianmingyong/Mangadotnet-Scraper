import json
import re
from collections.abc import AsyncIterable, Sequence
from typing import Final, Unpack, cast, override

from aiohttp import ClientResponseError
from bs4 import BeautifulSoup, Tag
from playwright.async_api import Browser, Error

from mangadotnet_scraper.camoufox_utils import (
    create_browser,
    handle_cloudflare_interstitial,
)
from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.base import (
    BaseModule,
    BaseModuleArgs,
    MangaChapter,
    MangaDetail,
    MangaListing,
    MangaPage,
)
from mangadotnet_scraper.modules.error import FetchError, SeriesNotFoundError
from mangadotnet_scraper.network import retryable_client_session
from mangadotnet_scraper.utilities import clean_string


class KeyoAppTemplate(BaseModule):
    group_name: Final[str]
    base_cdn_url: Final[str]

    def __init__(
        self,
        config: MangaDotNetScraperConfig,
        group_name: str,
        base_cdn_url: str,
        **kwargs: Unpack[BaseModuleArgs],
    ) -> None:
        super().__init__(config, **kwargs)

        self.group_name = group_name
        self.base_cdn_url = base_cdn_url

    @override
    async def on_fetch_manga_listing(self) -> AsyncIterable[MangaListing]:
        async with (
            create_browser() as browser,
            await cast(Browser, browser).new_context() as context,
        ):
            page = await context.new_page()

            target_page = f"{self.base_url}/latest"

            response = await handle_cloudflare_interstitial(page, target_page)

            if not response.ok and await response.header_value("cf-mitigated") != "challenge":
                raise FetchError(
                    f"Request returned {response.status} ({response.status_text}) for {target_page}"
                )

            while True:
                try:
                    await page.click(
                        'a[wire\\:click\\.prevent="loadMore"]',
                        strict=True,
                        timeout=5000,
                    )
                except Error:
                    break

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            elements = soup.find_all(
                "a", {"href": re.compile("/series/"), "class": "grid"}
            )

            for element in elements:
                link = cast(str, element.attrs.get("href"))
                title = cast(str, element.attrs.get("title"))
                series_id = link[link.rfind("/") + 1 :]

                if title is None or link is None:
                    continue

                yield MangaListing(
                    clean_string(series_id),
                    clean_string(title),
                    clean_string(link),
                )

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
        title = clean_string(title_element.text) if title_element else ""

        alt_titles_element = soup.find_all("li", attrs={"class": "select-all"})
        alt_titles = [clean_string(e.text) for e in alt_titles_element]

        def is_chapter_link_element(tag: Tag) -> bool:
            return (
                tag.name == "a"
                and tag.has_attr("href")
                and re.search("/read/", cast(str, tag.get("href", default="")))
                is not None
                and tag.find_parent("div", attrs={"id": "chapters"})
                is not None
            )

        chapters = []
        chapter_elements = soup.find_all(is_chapter_link_element)

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
                MangaChapter(
                    self.language,
                    self.group_name,
                    "chapter",
                    chapter_number,
                    None,
                    f"Chapter {chapter_number:.1f}".rstrip("0").rstrip("."),
                    f"{self.base_url}{chapter_link}"
                    if not chapter_link.startswith("http")
                    else chapter_link,
                    chapter_link[chapter_link.rfind("/") + 1 :],
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

        json_element = soup.find(
            "div", attrs={"x-data": re.compile("^immersiveReader")}
        )

        if json_element is None:
            return []

        pages = []

        json_str = cast(str, json_element.get("x-data", default="")).strip()
        match = re.search(
            r"pages\s*:\s*JSON\.parse\s*\(\s*(['\"])(.*?)\1\s*\)",
            json_str,
            re.DOTALL,
        )

        if match is None:
            # This is a premium chapter, we can't actually get the data here so we might as well guess?
            page = 1

            revision_element = soup.find("meta", {"property": "og:image"})

            if revision_element is None:
                return []

            revision_id = cast(str | None, revision_element.get("content"))

            if revision_id is not None and "/revisions/" not in revision_id:
                revision_id = None

            if revision_id is not None:
                revision_id = revision_id[: revision_id.rfind("/")]
                revision_id = revision_id[revision_id.rfind("/") + 1 :]

            @retryable_client_session
            async def test_page_response(link: str) -> bool:
                async with self.session.head(link) as response:
                    if response.ok:
                        return True
                    elif response.status == 404 or response.status == 403:
                        return False
                    else:
                        response.raise_for_status()

                return False

            while True:
                if revision_id is None:
                    image_link = f"{self.base_cdn_url}/series/webtoon/{manga_id}/chapters/{chapter_id}/{page:03d}.jpg"
                else:
                    image_link = f"{self.base_cdn_url}/series/webtoon/{manga_id}/chapters/{chapter_id}/revisions/{revision_id}/{page:03d}.jpg"

                if await test_page_response(image_link):
                    pages.append(MangaPage(page, image_link, None))
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
                                f"{page.get('path', '').replace('\\', '')}",
                                None,
                            )
                        )

        return pages
