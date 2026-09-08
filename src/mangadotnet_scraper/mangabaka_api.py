from collections import Counter
from collections.abc import Iterable, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Final, Literal, ReadOnly, TypedDict

from aiohttp import ClientSession

from mangadotnet_scraper.network import create_client, retryable_client_session


class MangaBakaError(TypedDict):
    status: ReadOnly[Literal[400, 404, 429, 500, 503, 504]]
    message: ReadOnly[str]


class MangaBakaEntry(TypedDict):
    status: ReadOnly[Literal[200]]
    data: ReadOnly[MangaBakaEntryData]


class MangaBakaEntries(TypedDict):
    status: ReadOnly[Literal[200]]
    data: Sequence[MangaBakaEntryData]


class MangaBakaEntryData(TypedDict):
    id: ReadOnly[int]
    titles: Sequence[MangaBakaEntryDataTitle]


class MangaBakaEntryDataTitle(TypedDict):
    title: ReadOnly[str]


class MangaBakaApi(AbstractAsyncContextManager):
    _BASE_API_URL = "https://api.mangabaka.org"

    _session: Final[ClientSession]

    def __init__(self):
        self._session = create_client(base_url=f"{self._BASE_API_URL}", headers={"Origin": self._BASE_API_URL})

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        await self.close()

    async def close(self):
        if self._session is not None:
            await self._session.close()

    @retryable_client_session
    async def get_entry_by_id(self, ids: int) -> MangaBakaEntryData | MangaBakaError:
        async with self._session.get(f"/v1/series/{ids}") as response:
            json: MangaBakaEntry | MangaBakaError = await response.json(encoding="utf-8")
            return json if json["status"] != 200 else json["data"]

    async def get_entry_by_title(self, titles: str | Iterable[str]) -> MangaBakaEntryData | None | MangaBakaError:
        if isinstance(titles, str):
            titles = [titles]

        matches: list[MangaBakaEntryData] = []

        for title in titles:
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
