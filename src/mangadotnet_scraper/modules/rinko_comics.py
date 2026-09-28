import json
import re
from collections.abc import AsyncIterable
from typing import Literal, ReadOnly, TypedDict, cast, override

from bs4 import BeautifulSoup, Tag

from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.base import BaseModule, MangaChapter, MangaDetail, MangaListing, MangaPage
from mangadotnet_scraper.utilities import clean_string, dict_get_recursive


class RinkoComicsModule(BaseModule):
    _BASE_URL = "https://rinkocomics.com"

    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        super().__init__(config, "rinko_comics", "Rinko Comics", self._BASE_URL)

    @override
    async def fetch_manga_listing(self) -> AsyncIterable[MangaListing]:
        page = 1
        has_next_page = True

        while has_next_page:
            html = await self.get_html(f"/comic/page/{page}/")
            soup = BeautifulSoup(html, "html.parser")

            def find_title(tag: Tag) -> bool:
                return (
                    tag.name == "a"
                    and re.search("/comic/", cast(str, tag.get("href", ""))) is not None
                    and tag.find_parent("h2", {"class": "ac-title"}) is not None
                )

            elements = soup.find_all(find_title)

            for element in elements:
                link = cast(str | None, element.get("href"))
                title = cast(str | None, element.get_text(strip=True))

                parent = element.find_parent("article", {"class": "ac-card"})
                series_id = None

                if parent is not None:
                    series_id = cast(str | None, parent.get("data-id"))

                if link is None or title is None or series_id is None:
                    continue

                yield MangaListing(clean_string(series_id), clean_string(title), clean_string(link))

            def has_next_page(tag: Tag) -> bool:
                return (
                    tag.name == "div"
                    and "ac-pagination" in tag.get_attribute_list("class")
                    and tag.find("a", {"class": re.compile("next")}) is not None
                )

            page_element = soup.find(has_next_page)
            has_next_page = page_element is not None
            page += 1

    class NextChapterResponse(TypedDict):
        success: ReadOnly[Literal["true"]]
        data: ReadOnly[RinkoComicsModule.NextChapterResponseData]

    class NextChapterResponseData(TypedDict):
        html: ReadOnly[str]

    @override
    async def fetch_manga_detail(self, manga_id: str, link: str) -> MangaDetail:
        html = await self.get_html(link)
        soup = BeautifulSoup(html, "html.parser")

        title_element = soup.find("h1")
        title = clean_string(title_element.get_text() if title_element is not None else "")

        alt_titles_element = soup.find_all("span", attrs={"class": "alt-title"})
        alt_titles = [clean_string(element.get_text()) for element in alt_titles_element]

        nonce_element = soup.find("script", {"id": "comicworld-loadmore-js-extra"})
        nonce = None

        if nonce_element is not None:
            nonce = nonce_element.get_text(strip=True)
            nonce = nonce[nonce.find("{") : nonce.rfind("}") + 1]
            nonce = json.loads(nonce)
            nonce = dict_get_recursive(nonce, "nonce")

        chapters = []

        async def load_next_chapters(nonce: str, offset: int) -> self.NextChapterResponse:
            async with self.session.post(
                "/wp-admin/admin-ajax.php",
                data={"action": "load_more_chapters", "nonce": nonce, "comic_id": manga_id, "offset": offset},
            ) as response:
                response.raise_for_status()
                return await response.json()

        def find_free_chapters(tag: Tag) -> bool:
            return (
                tag.name == "li"
                and "chapter" in tag.get_attribute_list("class")
                and "locked-chapter" not in tag.get_attribute_list("class")
            )

        def add_chapters(html: str) -> None:
            soup = BeautifulSoup(html, "html.parser")
            chapter_elements = soup.find_all(find_free_chapters)

            for chapter_element in chapter_elements:
                chapter_title = chapter_element.get("data-title")

                if chapter_title is None:
                    continue

                title_match = re.search("Chapter (\\d+|\\d+\\.\\d+)", cast(str, chapter_title))

                if title_match:
                    chapter_number = float(title_match[1])
                else:
                    continue

                chapter_link = cast(str | None, chapter_element.get("data-permalink"))

                if chapter_link is None:
                    continue

                chapter_id = cast(str | None, chapter_element.get("data-post-id"))

                if chapter_id is None:
                    continue

                chapters.append(
                    MangaChapter(
                        "en",
                        self.display_name,
                        "chapter",
                        chapter_number,
                        None,
                        f"Chapter {chapter_number:.1f}".rstrip("0").rstrip("."),
                        chapter_link,
                        chapter_id,
                    )
                )

        add_chapters(html)

        offset = 10

        while True:
            if nonce is None:
                break

            json_chapters = await load_next_chapters(nonce, offset)
            inner_html = dict_get_recursive(json_chapters, "data", "html")

            if inner_html is None or inner_html == "":
                break

            add_chapters(inner_html)

            offset += 10

        return MangaDetail(title, alt_titles, chapters)

    @override
    async def fetch_manga_pages(
        self, manga_id: str, manga_link: str, chapter_id: str, chapter_link: str
    ) -> list[MangaPage]:
        html = await self.get_html(chapter_link)
        soup = BeautifulSoup(html, "html.parser")

        def find_images(tag: Tag) -> bool:
            return tag.name == "img" and "chapter-image" in tag.get_attribute_list("class")

        image_elements = soup.find_all(find_images)
        images = []

        for image_element in image_elements:
            page = cast(str, image_element.get("data-page"))
            src = cast(str, image_element.get("data-src"))

            if page is None or src is None:
                return []

            images.append(MangaPage(int(page), src, None))

        return images
