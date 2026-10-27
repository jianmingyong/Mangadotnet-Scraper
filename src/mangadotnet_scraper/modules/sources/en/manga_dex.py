from collections.abc import AsyncIterable, Mapping, Sequence
from typing import ReadOnly, TypedDict, cast, override

from aiohttp import ClientResponseError

from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.base import (
    BaseModule,
    MangaChapter,
    MangaDetail,
    MangaListing,
    MangaPage,
)
from mangadotnet_scraper.modules.error import SeriesNotFoundError
from mangadotnet_scraper.modules.manager import ModuleManager
from mangadotnet_scraper.utilities import dict_get_recursive


class MangaListResponse(TypedDict):
    data: ReadOnly[Sequence[MangaListResponseData]]
    limit: ReadOnly[int]
    offset: ReadOnly[int]
    total: ReadOnly[int]


class MangaListResponseData(TypedDict):
    id: ReadOnly[str]
    type: ReadOnly[str]
    attributes: ReadOnly[MangaListResponseDataAttribute]


class MangaListResponseDataAttribute(TypedDict):
    title: ReadOnly[Mapping[str, str]]
    altTitles: ReadOnly[Sequence[Mapping[str, str]]]


class MangaDetailResponse(TypedDict):
    data: ReadOnly[MangaDetailResponseData]


class MangaDetailResponseData(TypedDict):
    attributes: ReadOnly[MangaListResponseDataAttribute]


class MangaFeedResponse(TypedDict):
    data: ReadOnly[Sequence[MangaFeedResponseData]]
    limit: ReadOnly[int]
    offset: ReadOnly[int]
    total: ReadOnly[int]


class MangaFeedResponseData(TypedDict):
    id: ReadOnly[str]
    type: ReadOnly[str]
    attributes: ReadOnly[MangaFeedResponseDataAttribute]
    relationships: ReadOnly[Sequence[MangaFeedResponseDataRelationship]]


class MangaFeedResponseDataAttribute(TypedDict):
    volume: ReadOnly[str | None]
    chapter: ReadOnly[str]
    title: ReadOnly[str | None]
    translatedLanguage: ReadOnly[str]
    isUnavailable: ReadOnly[bool]


class MangaFeedResponseDataRelationship(TypedDict):
    id: ReadOnly[str]
    type: ReadOnly[str]


class MangaPageResponse(TypedDict):
    baseUrl: ReadOnly[str]
    hash: ReadOnly[str]
    chapter: ReadOnly[MangaPageResponseChapter]


class MangaPageResponseChapter(TypedDict):
    data: ReadOnly[Sequence[str]]


class MangaDexModule(BaseModule):
    def __init__(self, config: MangaDotNetScraperConfig):
        super().__init__(
            config,
            module_id="manga_dex",
            display_name="MangaDex",
            language="multi",
            version=1,
            base_url="https://mangadex.org",
            base_api_url="https://api.mangadex.org",
            additional_headers={
                "Origin": "https://mangadex.org",
                "Referer": "https://mangadex.org/",
            },
        )

    @override
    async def on_fetch_manga_listing(self) -> AsyncIterable[MangaListing]:
        async def fetch_listing_json(
            group: str, offset: int = 0
        ) -> MangaListResponse:
            return await self.get_json(
                "/manga",
                params={
                    "limit": 100,
                    "offset": offset,
                    "contentRating[]": [
                        "safe",
                        "suggestive",
                        "erotica",
                        "pornographic",
                    ],
                    "group": group,
                },
            )

        # groups to fetch
        groups: dict[str, str] = self.config.get_module_config(
            self.module_id, "groups", {}
        )
        fetched_ids = set()

        for group in groups:
            offset = 0
            has_next_page = True

            while has_next_page:
                json = await fetch_listing_json(group, offset)

                for data in dict_get_recursive(json, "data", default=[]):
                    manga_id = dict_get_recursive(data, "id")

                    if manga_id in fetched_ids:
                        continue

                    fetched_ids.add(manga_id)

                    title = next(
                        iter(
                            cast(
                                Mapping,
                                dict_get_recursive(
                                    data, "attributes", "title", default={}
                                ),
                            ).values()
                        )
                    )

                    if title is None:
                        continue

                    yield MangaListing(
                        manga_id, title, f"{self.base_url}/title/{manga_id}"
                    )

                offset += 100
                has_next_page = offset < dict_get_recursive(
                    data, "total", default=0
                )

    @override
    async def on_fetch_manga_detail(
        self, manga_id: str, link: str
    ) -> MangaDetail:
        try:
            detail: MangaDetailResponse = await self.get_json(
                f"/manga/{manga_id}"
            )
        except ClientResponseError as error:
            if error.code == 404:
                raise SeriesNotFoundError() from error
            else:
                raise

        title = next(
            iter(
                cast(
                    Mapping,
                    dict_get_recursive(
                        detail, "data", "attributes", "title", default={}
                    ),
                ).values()
            )
        )

        alt_titles = [
            cast(str, next(iter(cast(Mapping, x).values())))
            for x in dict_get_recursive(
                detail, "data", "attributes", "altTitles", default=[]
            )
        ]

        async def get_feed(offset: int = 0) -> MangaFeedResponse:
            return await self.get_json(
                f"/manga/{manga_id}/feed",
                params={
                    "limit": 100,
                    "offset": offset,
                    "contentRating[]": [
                        "safe",
                        "suggestive",
                        "erotica",
                        "pornographic",
                    ],
                    "includeFutureUpdates": "0",
                    "order[volume]": "desc",
                    "order[chapter]": "desc",
                    "includes[]": ["scanlation_group"],
                },
            )

        chapters = []

        # groups to fetch
        groups: dict[str, str] = self.config.get_module_config(
            self.module_id, "groups", {}
        )

        offset = 0
        has_next_page = True

        while has_next_page:
            feed = await get_feed(offset)

            for chapter in dict_get_recursive(feed, "data", default=[]):
                type = dict_get_recursive(chapter, "type")

                if type != "chapter":
                    continue

                chapter_id = dict_get_recursive(chapter, "id")
                volume = dict_get_recursive(chapter, "attributes", "volume")
                chapter_number = dict_get_recursive(
                    chapter, "attributes", "chapter"
                )
                chapter_title: str = dict_get_recursive(
                    chapter, "attributes", "title"
                )
                language = dict_get_recursive(
                    chapter, "attributes", "translatedLanguage"
                )

                group_id = None

                for relationship in dict_get_recursive(
                    chapter, "relationships", default=[]
                ):
                    if (
                        dict_get_recursive(relationship, "type")
                        == "scanlation_group"
                    ):
                        group_id = dict_get_recursive(relationship, "id")
                        break

                if group_id is None or group_id not in groups:
                    continue

                if (
                    chapter_id is None
                    or chapter_number is None
                    or language is None
                ):
                    continue

                chapters.append(
                    MangaChapter(
                        language,
                        groups[group_id],
                        type,
                        float(chapter_number),
                        float(volume) if volume is not None else None,
                        chapter_title
                        if chapter_title is not None
                        and chapter_title.strip() != ""
                        else f"Chapter {chapter_number}",
                        f"{self.base_url}/chapter/{chapter_id}",
                        chapter_id,
                    )
                )

            offset += 100
            has_next_page = offset < dict_get_recursive(
                feed, "total", default=0
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
        page: MangaPageResponse = await self.get_json(
            f"/at-home/server/{chapter_id}"
        )

        base_url = dict_get_recursive(page, "baseUrl")
        hash = dict_get_recursive(page, "chapter", "hash")
        data = dict_get_recursive(page, "chapter", "data", default=[])

        if base_url is None or hash is None or data is None:
            return []

        pages = []

        for index, url in enumerate(data):
            pages.append(MangaPage(index, f"{base_url}/data/{hash}/{url}"))

        return pages


ModuleManager.register_module(MangaDexModule)
