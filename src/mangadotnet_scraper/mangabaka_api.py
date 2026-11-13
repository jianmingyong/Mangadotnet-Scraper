from collections import Counter
from collections.abc import Iterable, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Final, Literal, ReadOnly, TypedDict, override

from mangadotnet_scraper.network import (
    HttpClient,
    Response,
    create_http_client,
    retryable_client_method,
)


class MangaBakaEntry(TypedDict):
    status: ReadOnly[Literal[200]]
    data: ReadOnly[MangaBakaEntryData]


class MangaBakaEntries(TypedDict):
    status: ReadOnly[Literal[200]]
    data: ReadOnly[Sequence[MangaBakaEntryData]]


class MangaBakaEntryData(TypedDict):
    id: ReadOnly[int]
    titles: ReadOnly[Sequence[MangaBakaEntryDataTitle]]


class MangaBakaEntryDataTitle(TypedDict):
    title: ReadOnly[str]


class MangaBakaApi(AbstractAsyncContextManager):
    _client: Final[HttpClient]

    def __init__(self) -> None:
        self._client = create_http_client("https://api.mangabaka.org")

    @override
    async def __aexit__(self, *args) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.close()

    @retryable_client_method
    async def get_series_by_id(self, id: int) -> MangaBakaEntry:
        async with await self._client.get(f"/v2/series/{id}") as response:
            response: Response
            response.raise_for_status()
            return await response.json()

    @retryable_client_method
    async def match_series_by_title(self, title: str) -> MangaBakaEntries:
        async with await self._client.get(
            "/v2/series/match",
            params={
                "q": title,
                "type_not": "novel",
                "limit": 10,
                "schema": "full",
            },
        ) as response:
            response: Response
            response.raise_for_status()
            return await response.json()

    @retryable_client_method
    async def search_series_by_title(self, title: str) -> MangaBakaEntries:
        async with await self._client.get(
            "/v2/series/search",
            params={
                "q": title,
                "type_not": "novel",
                "page": 1,
                "limit": 10,
                "schema": "full",
            },
        ) as response:
            response: Response
            response.raise_for_status()
            return await response.json()

    async def get_id_by_title(self, titles: str | Iterable[str]) -> int | None:
        if isinstance(titles, str):
            titles = [titles]

        matches: list[MangaBakaEntryData] = []

        async def do_exact_match(title: str) -> None:
            json = await self.match_series_by_title(title)

            for data in json.get("data", []):
                for matched_title in data.get("titles", []):
                    match_base = title.casefold()
                    match_target = matched_title.get("title", "").casefold()

                    if match_base == match_target:
                        matches.append(data)
                        break

        for title in titles:
            await do_exact_match(title)

        async def do_search(title: str) -> None:
            json = await self.search_series_by_title(title)

            for data in json.get("data", []):
                for matched_title in data.get("titles", []):
                    match_base = title.casefold()
                    match_target = matched_title.get("title", "").casefold()

                    if len(match_target) > 20:
                        matches.append(data)
                        break

                    if match_base == match_target:
                        matches.append(data)
                        break

        if len(matches) == 0:
            for title in titles:
                await do_search(title)

        if len(matches) == 0:
            return None

        count = Counter(json_data.get("id", 0) for json_data in matches)
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

        return common_id
