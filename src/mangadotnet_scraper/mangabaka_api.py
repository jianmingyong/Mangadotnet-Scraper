from collections import Counter
from collections.abc import Collection, Iterable
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Final, Literal, ReadOnly, TypedDict

from aiohttp import ClientResponse, ClientResponseError, ClientSession

from mangadotnet_scraper.network import create_client, retryable_client_session
from mangadotnet_scraper.utilities import dict_get_recursive


class MangaBakaError(TypedDict):
    status: ReadOnly[Literal[400, 404, 429, 500, 503, 504]]
    message: ReadOnly[str]


class MangaBakaEntry(TypedDict):
    status: ReadOnly[Literal[200]]
    data: ReadOnly[MangaBakaEntryData]


class MangaBakaEntries(TypedDict):
    status: ReadOnly[Literal[200]]
    data: ReadOnly[Collection[MangaBakaEntryData]]


class MangaBakaEntryData(TypedDict):
    id: ReadOnly[int]
    titles: ReadOnly[Collection[MangaBakaEntryDataTitle]]


class MangaBakaEntryDataTitle(TypedDict):
    title: ReadOnly[str]


class MangaBakaApi(AbstractAsyncContextManager):
    _BASE_API_URL = "https://api.mangabaka.org"

    _session: Final[ClientSession]

    def __init__(self) -> None:
        self._session = create_client(self._BASE_API_URL, headers={"Origin": self._BASE_API_URL})

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        await self._session.close()

    async def _raise_for_status(self, response: ClientResponse) -> None:
        if not response.ok:
            assert response.reason is not None

            message = response.reason

            if response.content_type == "application/json":
                json: MangaBakaError = await response.json()
                error_message: str | None = dict_get_recursive(json, "message")
                if error_message is not None:
                    message = error_message

            raise ClientResponseError(
                response.request_info,
                response.history,
                status=response.status,
                message=message,
                headers=response.headers,
            )

    @retryable_client_session
    async def get_entry_by_id(self, ids: int) -> MangaBakaEntryData:
        async with self._session.get(f"/v2/series/{ids}") as response:
            await self._raise_for_status(response)
            return dict_get_recursive(await response.json(), "data", default={})

    async def get_entry_by_title(self, titles: str | Iterable[str]) -> MangaBakaEntryData | None:
        if isinstance(titles, str):
            titles = [titles]

        matches: list[MangaBakaEntryData] = []

        @retryable_client_session
        async def do_exact_match(title: str) -> None:
            async with self._session.get(
                "/v2/series/match",
                params={
                    "q": title,
                    "type_not": "novel",
                },
            ) as response:
                await self._raise_for_status(response)

                json: MangaBakaEntries = await response.json(encoding="utf-8")

                for data in dict_get_recursive(json, "data", default=[]):
                    for inner_title in dict_get_recursive(data, "titles", default=[]):
                        if title == dict_get_recursive(inner_title, "title"):
                            matches.append(data)
                            break

        for title in titles:
            await do_exact_match(title)

        @retryable_client_session
        async def do_search(title: str) -> None:
            async with self._session.get(
                "/v2/series/search",
                params={
                    "q": title,
                    "type_not": "novel",
                },
            ) as response:
                await self._raise_for_status(response)

                json: MangaBakaEntries = await response.json(encoding="utf-8")

                for data in dict_get_recursive(json, "data", default=[]):
                    for inner_title in dict_get_recursive(data, "titles", default=[]):
                        if title == dict_get_recursive(inner_title, "title"):
                            matches.append(data)
                            break

        if len(matches) == 0:
            for title in titles:
                await do_search(title)

        if len(matches) == 0:
            return None

        count = Counter(dict_get_recursive(json_data, "id", default=0) for json_data in matches)
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
            if dict_get_recursive(json_data, "id") == common_id:
                return json_data

        return None
