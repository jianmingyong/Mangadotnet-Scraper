import json
import mimetypes
import re
from abc import abstractmethod
from collections.abc import AsyncGenerator, AsyncIterable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from re import Match
from typing import Any, Final

from aiohttp import ClientSession
from bs4 import BeautifulSoup, ResultSet, Tag
from bs4.element import AttributeValueList

from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.network import RetryMiddleware, create_client
from mangadotnet_scraper.utilities import clean_string


@dataclass(frozen=True)
class MangaDetail:
    title: str
    alt_titles: list[str]
    chapters: list[MangaChapter]


@dataclass(frozen=True)
class MangaChapter:
    language: str
    group: str
    number: int | float
    title: str
    link: str


@dataclass(frozen=True)
class MangaPage:
    number: int
    link: str
    data: dict[str, Any]


@dataclass(frozen=True)
class MangaImage:
    filename: str
    data: bytes


class BaseModule(AbstractAsyncContextManager):
    _config: Final[MangaDotNetScraperConfig]

    module_id: Final[str]
    display_name: Final[str]

    def __init__(self, config: MangaDotNetScraperConfig, module_id: str, display_name: str) -> None:
        self._config = config
        self.module_id = module_id
        self.display_name = display_name

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb) -> None:
        await self.close()

    async def initialize(self) -> None:
        pass

    async def close(self) -> None:
        pass

    @abstractmethod
    def fetch_manga_listing(self) -> AsyncIterable[tuple[str, str]]:
        raise NotImplementedError()

    @abstractmethod
    async def fetch_manga_detail(self, link: str) -> MangaDetail:
        raise NotImplementedError()

    @abstractmethod
    async def fetch_manga_pages(self, manga_link: str, chapter_link: str) -> list[MangaPage]:
        raise NotImplementedError()

    @abstractmethod
    async def fetch_manga_image(self, page: MangaPage) -> MangaImage:
        raise NotImplementedError()


class ArtLapsaModule(BaseModule):
    _BASE_URL = "https://artlapsa.com"

    _session: Final[ClientSession]

    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        super().__init__(config, "art_lapsa", "Art Lapsa")
        self._session = create_client(base_url=self._BASE_URL)

    async def close(self) -> None:
        await self._session.close()

    async def fetch_manga_listing(self) -> AsyncGenerator[tuple[str, str]]:
        async with self._session.get("/latest/") as response:
            response.raise_for_status()

            html: str = await response.text("utf-8")
            soup = BeautifulSoup(html, "html.parser")

            elements: ResultSet[Tag] = soup.find_all("a", {"href": re.compile("/series/"), "class": "grid"})

            for element in elements:
                yield clean_string(str(element.attrs.get("title"))), clean_string(str(element.attrs.get("href")))

    async def fetch_manga_detail(self, link: str) -> MangaDetail:
        async with self._session.get(link) as response:
            response.raise_for_status()

            html: str = await response.text("utf-8")
            soup = BeautifulSoup(html, "html.parser")

            title_element = soup.find("h1")
            title: str = clean_string(title_element.text) if title_element else ""

            alt_titles_element: ResultSet[Tag] = soup.find_all("span", attrs={"class": "select-all"})
            alt_titles: list[str] = [clean_string(e.text) for e in alt_titles_element]

            def is_chapter_link_element(tag: Tag) -> bool:
                return (
                    tag.name == "a"
                    and tag.has_attr("href")
                    and re.compile("/read/").search(str(tag.attrs["href"])) is not None
                    and tag.find_parent("div", attrs={"id": "chapters"}) is not None
                )

            chapter_elements: ResultSet[Tag] = soup.find_all(is_chapter_link_element)
            chapters: list[MangaChapter] = []

            for chapter_element in chapter_elements:
                chapter_title: AttributeValueList | str | None = chapter_element.attrs.get("title")
                if not chapter_title or not isinstance(chapter_title, str):
                    continue

                title_match: Match[str] | None = re.compile("Chapter (\\d+|\\d+\\.\\d+)").search(chapter_title)
                if title_match:
                    chapter_number = float(title_match[1])
                else:
                    continue

                chapter_link = str(chapter_element.attrs.get("href"))

                chapters.append(
                    MangaChapter(
                        "en",
                        self.display_name,
                        chapter_number,
                        f"Chapter {chapter_number:.1f}".rstrip("0").rstrip("."),
                        f"{self._BASE_URL}{chapter_link}",
                    )
                )

            return MangaDetail(title, alt_titles, chapters)

    async def fetch_manga_pages(self, manga_link: str, chapter_link: str):
        async with self._session.get(chapter_link) as response:
            response.raise_for_status()

            html: str = await response.text("utf-8")
            soup = BeautifulSoup(html, "html.parser")

            json_element = soup.find("div", attrs={"x-data": re.compile("^immersiveReader")})

            if json_element is None:
                return []

            json_str: str = str(json_element.attrs.get("x-data")).strip()
            json_str = json_str[16:-1].replace("\\/", "/").replace("'", '"')
            json_str = re.sub(r"([{,]\s*)([A-Za-z_$][A-Za-z0-9_$]*)\s*:", r'\1"\2":', json_str)

            try:
                json_obj = json.loads(json_str)
            except json.decoder.JSONDecodeError:
                return []

            pages: list[MangaPage] = []

            if isinstance(json_obj, dict):
                json_pages = json_obj.get("pages", [])

                if len(json_pages) == 0:
                    # This is a premium chapter, we can't actually get the data here so we might as well guess?
                    series_id = manga_link[manga_link.rfind("/") + 1 :]
                    chapter_id = chapter_link[chapter_link.rfind("/") + 1 :]
                    page = 1

                    while True:
                        test_link = (
                            f"{self._BASE_URL}/storage/series/webtoon/{series_id}/chapters/{chapter_id}/{page:03d}.jpg"
                        )
                        async with self._session.get(
                            test_link, middlewares=(*self._session._middlewares, RetryMiddleware(1))
                        ) as test_response:
                            if test_response.ok:
                                pages.append(
                                    MangaPage(page, test_link, {"format": "jpg", "size": test_response.content_length})
                                )
                                page += 1
                            else:
                                break
                else:
                    for i, page in zip(range(len(json_pages)), json_pages):
                        if isinstance(page, dict):
                            pages.append(
                                MangaPage(
                                    i,
                                    f"{json_obj.get('baseLink')}{page.get('path')}",
                                    {
                                        "width": page.get("width"),
                                        "height": page.get("height"),
                                        "format": page.get("format"),
                                        "size": page.get("size"),
                                    },
                                )
                            )

            return pages

    async def fetch_manga_image(self, page: MangaPage) -> MangaImage:
        async with self._session.get(
            page.link, middlewares=(*self._session._middlewares, RetryMiddleware())
        ) as response:
            response.raise_for_status()

            filename = f"{page.number:03d}{mimetypes.guess_extension(response.content_type)}"
            data = await response.read()

            return MangaImage(filename, data)


class RitharScansModule(BaseModule):
    _BASE_URL = "https://ritharscans.com"

    _session: Final[ClientSession]

    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        super().__init__(config, "rithar_scans", "Rithar Scans")
        self._session = create_client(base_url=self._BASE_URL)

    async def close(self) -> None:
        await self._session.close()

    async def fetch_manga_listing(self) -> AsyncGenerator[tuple[str, str]]:
        async with self._session.get("/latest") as response:
            response.raise_for_status()

            html: str = await response.text("utf-8")
            soup = BeautifulSoup(html, "html.parser")

            elements: ResultSet[Tag] = soup.find_all("a", {"href": re.compile("/series/"), "class": "grid"})

            for element in elements:
                yield clean_string(str(element.attrs.get("title"))), clean_string(str(element.attrs.get("href")))

    async def fetch_manga_detail(self, link: str) -> MangaDetail:
        async with self._session.get(link) as response:
            response.raise_for_status()

            html: str = await response.text("utf-8")
            soup = BeautifulSoup(html, "html.parser")

            title_element = soup.find("h1")
            title: str = clean_string(title_element.text) if title_element else ""

            alt_titles_element: ResultSet[Tag] = soup.find_all("span", attrs={"class": "select-all"})
            alt_titles: list[str] = [clean_string(e.text) for e in alt_titles_element]

            def is_chapter_link_element(tag: Tag) -> bool:
                return (
                    tag.name == "a"
                    and tag.has_attr("href")
                    and re.compile("/read/").search(str(tag.attrs["href"])) is not None
                    and tag.find_parent("div", attrs={"id": "chapters"}) is not None
                )

            chapter_elements: ResultSet[Tag] = soup.find_all(is_chapter_link_element)
            chapters: list[MangaChapter] = []

            for chapter_element in chapter_elements:
                chapter_title: AttributeValueList | str | None = chapter_element.attrs.get("title")
                if not chapter_title or not isinstance(chapter_title, str):
                    continue

                title_match: Match[str] | None = re.compile("Chapter (\\d+|\\d+\\.\\d+)").search(chapter_title)
                if title_match:
                    chapter_number = float(title_match[1])
                else:
                    continue

                chapter_link = str(chapter_element.attrs.get("href"))

                chapters.append(
                    MangaChapter(
                        "en",
                        self.display_name,
                        chapter_number,
                        f"Chapter {chapter_number:.1f}".rstrip("0").rstrip("."),
                        f"{self._BASE_URL}{chapter_link}",
                    )
                )

            return MangaDetail(title, alt_titles, chapters)

    async def fetch_manga_pages(self, manga_link: str, chapter_link: str):
        async with self._session.get(chapter_link) as response:
            response.raise_for_status()

            html: str = await response.text("utf-8")
            soup = BeautifulSoup(html, "html.parser")

            json_element = soup.find("div", attrs={"x-data": re.compile("^immersiveReader")})

            if json_element is None:
                return []

            json_str: str = str(json_element.attrs.get("x-data")).strip()
            json_str = json_str[16:-1].replace("\\/", "/").replace("'", '"')
            json_str = re.sub(r"([{,]\s*)([A-Za-z_$][A-Za-z0-9_$]*)\s*:", r'\1"\2":', json_str)

            try:
                json_obj = json.loads(json_str)
            except json.decoder.JSONDecodeError:
                return []

            pages: list[MangaPage] = []

            if isinstance(json_obj, dict):
                json_pages = json_obj.get("pages", [])

                if len(json_pages) == 0:
                    # This is a premium chapter, we can't actually get the data here so we might as well guess?
                    series_id = manga_link[manga_link.rfind("/") + 1 :]
                    chapter_id = chapter_link[chapter_link.rfind("/") + 1 :]
                    page = 1

                    while True:
                        test_link = (
                            f"{self._BASE_URL}/storage/series/webtoon/{series_id}/chapters/{chapter_id}/{page:03d}.jpg"
                        )
                        async with self._session.get(
                            test_link, middlewares=(*self._session._middlewares, RetryMiddleware(1))
                        ) as test_response:
                            if test_response.ok:
                                pages.append(
                                    MangaPage(page, test_link, {"format": "jpg", "size": test_response.content_length})
                                )
                                page += 1
                            else:
                                break
                else:
                    for i, page in zip(range(len(json_pages)), json_pages):
                        if isinstance(page, dict):
                            pages.append(
                                MangaPage(
                                    i,
                                    f"{json_obj.get('baseLink')}{page.get('path')}",
                                    {
                                        "width": page.get("width"),
                                        "height": page.get("height"),
                                        "format": page.get("format"),
                                        "size": page.get("size"),
                                    },
                                )
                            )

            return pages

    async def fetch_manga_image(self, page: MangaPage) -> MangaImage:
        async with self._session.get(
            page.link, middlewares=(*self._session._middlewares, RetryMiddleware())
        ) as response:
            response.raise_for_status()

            filename = f"{page.number:03d}{mimetypes.guess_extension(response.content_type)}"
            data = await response.read()

            return MangaImage(filename, data)
