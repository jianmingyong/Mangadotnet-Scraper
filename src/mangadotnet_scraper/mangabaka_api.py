from collections import Counter
from contextlib import AbstractAsyncContextManager
from typing import Final, Literal, TypedDict

from aiohttp import ClientSession
from asynciolimiter import LeakyBucketLimiter

from mangadotnet_scraper.network import create_client


class MangaBakaError(TypedDict):
    status: Literal[400, 404, 429, 500, 503, 504]
    message: str


class MangaBakaEntry(TypedDict):
    status: Literal[200]
    data: MangaBakaEntryData


class MangaBakaEntries(TypedDict):
    status: Literal[200]
    data: list[MangaBakaEntryData]


class MangaBakaEntryData(TypedDict):
    id: int
    titles: list[MangaBakaEntryDataTitle]


class MangaBakaEntryDataTitle(TypedDict):
    title: str


class MangaBakaApi(AbstractAsyncContextManager):
    _BASE_API_URL = "https://api.mangabaka.org"

    _default_limiter: Final[LeakyBucketLimiter]
    _search_limiter: Final[LeakyBucketLimiter]
    _session: Final[ClientSession]

    def __init__(self):
        self._default_limiter = LeakyBucketLimiter(180 / 60, capacity=135)
        self._search_limiter = LeakyBucketLimiter(30 / 60, capacity=23)
        self._session = create_client(base_url=f"{self._BASE_API_URL}")

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        await self.close()

    async def close(self):
        self._default_limiter.close()
        self._search_limiter.close()

        if self._session is not None:
            await self._session.close()

    async def get_entry_by_id(self, ids: int) -> MangaBakaEntryData | MangaBakaError:
        await self._default_limiter.wait()
        async with self._session.get(f"/v1/series/{ids}") as response:
            json: MangaBakaEntry | MangaBakaError = await response.json(encoding="utf-8")
            return json if json["status"] != 200 else json["data"]

    async def get_entry_by_title(self, titles: str | list[str]) -> MangaBakaEntryData | None | MangaBakaError:
        if isinstance(titles, str):
            titles = [titles]

        matches: list[MangaBakaEntryData] = []

        for title in titles:
            await self._default_limiter.wait()

            async with await self._session.get(
                "/v1/series/match",
                params={
                    "q": title,
                    "type_not": "novel",
                },
            ) as response:
                json: MangaBakaEntries | MangaBakaError = await response.json(encoding="utf-8")

                if json["status"] != 200:
                    return json

                matches.extend(json["data"])

        if len(matches) == 0:
            for title in titles:
                await self._search_limiter.wait()

                async with self._session.get(
                    "/v1/series/search",
                    params={
                        "q": title,
                        "type_not": "novel",
                    },
                ) as response:
                    json: MangaBakaEntries | MangaBakaError = await response.json(encoding="utf-8")

                    if json["status"] != 200:
                        return json

                    matches.extend(json["data"])

        if len(matches) == 0:
            return None

        count = Counter(json_data["id"] for json_data in matches)
        common = count.most_common()

        common_id = None
        max_freq = 0
        duplicate = False

        for match_id, freq in common:
            if freq > max_freq:
                max_freq = freq
                common_id = match_id
                continue

            if freq == max_freq:
                duplicate = True
                break

        if duplicate:
            return None

        for json_data in matches:
            if json_data["id"] == common_id:
                return json_data

        return None
