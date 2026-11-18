import asyncio
import json
import logging
from abc import ABC, abstractmethod
from asyncio import create_task, sleep, wait
from base64 import b64encode
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from math import floor
from typing import (
    IO,
    Any,
    Final,
    Literal,
    NotRequired,
    ReadOnly,
    Self,
    TypedDict,
    cast,
    override,
)

from aiohttp import (
    ClientHandlerType,
    ClientRequest,
    ClientResponse,
    FormData,
)
from playwright.async_api import (
    Browser,
    ElementHandle,
    Error,
    TimeoutError,
)
from playwright.async_api import (
    Response as PlaywrightResponse,
)
from playwright_captcha import ClickSolver, FrameworkType

from mangadotnet_scraper.camoufox_utils import (
    create_browser,
    solve_cloudflare_captcha_interstitial,
    solve_cloudflare_captcha_turnstile,
)
from mangadotnet_scraper.config import ConfigProvider
from mangadotnet_scraper.network import (
    HttpClientProvider,
    HttpResponseError,
    create_http_client,
    retryable_client_method,
)
from mangadotnet_scraper.network.providers.aiohttp import (
    CloudflareMiddleware,
    Middleware,
    RateLimitedMiddleware,
    ServerRateLimitMiddleware,
    UserRateLimitMiddleware,
)
from mangadotnet_scraper.utilities import dict_get_recursive


class MangaDotNetResponseError(TypedDict):
    success: NotRequired[ReadOnly[Literal[False]]]
    error: ReadOnly[str]


class MangaDotNetProfile(TypedDict):
    profile: ReadOnly[MangaDotNetProfileData]


class MangaDotNetProfileData(TypedDict):
    id: ReadOnly[str]
    username: ReadOnly[str]
    email: ReadOnly[str]


class MangaDotNetSearch(TypedDict):
    manga_list: ReadOnly[Sequence[MangaDotNetSearchMangaList]]


class MangaDotNetSearchMangaList(TypedDict):
    id: ReadOnly[int]
    title: ReadOnly[str]


class MangaDotNetMangaEntry(TypedDict):
    manga: ReadOnly[MangaDotNetMangaEntryData]


class MangaDotNetMangaEntryData(TypedDict):
    id: ReadOnly[int]
    title: ReadOnly[str]
    alt_titles: ReadOnly[Sequence[str]]


class MangaDotNetChapterList(TypedDict):
    id: ReadOnly[int]
    chapter_number: ReadOnly[float | None]
    volume_number: ReadOnly[float | None]
    language: ReadOnly[str]
    groups: ReadOnly[Sequence[MangaDotNetChapterListGroup]]


class MangaDotNetChapterListGroup(TypedDict):
    id: ReadOnly[int]
    name: ReadOnly[str]
    slug: ReadOnly[str]
    is_scanlator: ReadOnly[bool]


class MangaDotNetVolumeList(TypedDict):
    id: ReadOnly[int]
    volume_number: ReadOnly[float]
    language: ReadOnly[str]
    groups: ReadOnly[Sequence[MangaDotNetChapterListGroup]]


class MangaDotNetGroupList(TypedDict):
    groups: ReadOnly[Sequence[MangaDotNetGroupListData]]


class MangaDotNetGroupListData(TypedDict):
    id: ReadOnly[int]
    name: ReadOnly[str]


class MangaDotNetFetchMangaBakaError(MangaDotNetResponseError):
    duplicate: ReadOnly[MangaDotNetFetchMangaBakaDuplicate]


class MangaDotNetFetchMangaBakaDuplicate(TypedDict):
    id: ReadOnly[int]
    title: ReadOnly[str]


class MangaDotNetFetchMangaBaka(TypedDict):
    success: ReadOnly[Literal[True]]
    data: ReadOnly[MangaDotNetFetchMangaBakaData]


class MangaDotNetFetchMangaBakaData(TypedDict):
    title: ReadOnly[str]
    description: ReadOnly[str]
    status: ReadOnly[str]
    hiatus: ReadOnly[str]
    country_of_origin: ReadOnly[str]
    genres: ReadOnly[Sequence[str]]
    alt_titles: ReadOnly[Sequence[str]]
    authors: ReadOnly[str]
    artists: ReadOnly[str]
    year: ReadOnly[int]
    content_rating: ReadOnly[str]
    rating: ReadOnly[float | None]
    tags: ReadOnly[Sequence[str]]
    anilist_id: ReadOnly[int | None]
    mangaupdates_id: ReadOnly[str | None]
    mangabaka_id: ReadOnly[int]
    cover_url: ReadOnly[str | None]
    banner_url: ReadOnly[str | None]
    source_url: ReadOnly[str]


class MangaDotNetCreateFromMangaBakaResponse(TypedDict):
    manga: ReadOnly[MangaDotNetCreateFromMangaBakaResponseManga]


class MangaDotNetCreateFromMangaBakaResponseManga(TypedDict):
    id: ReadOnly[int]
    title: ReadOnly[str]


class MangaDotNetBatchInitResponse(TypedDict):
    success: ReadOnly[Literal[True]]
    batch_id: ReadOnly[str]


class MangaDotNetBatchCompleteResponse(TypedDict):
    success: ReadOnly[Literal[True]]


@dataclass(frozen=True)
class MangaDotNetTusCapabilities:
    supported_versions: Sequence[str]
    max_file_size: int
    supported_extensions: Sequence[str]


class MangaDotNetLoginRequestHandler(ABC):
    @abstractmethod
    async def request_credentials(self) -> tuple[str | None, str | None]: ...

    @abstractmethod
    async def request_otp(self) -> str | None: ...


class MangaDotNetLoginMiddleware(Middleware):
    _AUTHENTICATION_COOKIE = "ory_kratos_session"

    _config: Final[ConfigProvider]

    def __init__(
        self,
        config: ConfigProvider,
    ) -> None:
        self._config = config

    @property
    def user_session_cookie(self) -> str | None:
        return self._config.mangadotnet_user_session

    @user_session_cookie.setter
    def user_session_cookie(self, value: str | None) -> None:
        self._config.mangadotnet_user_session = value

    async def __call__(
        self, request: ClientRequest, handler: ClientHandlerType
    ) -> ClientResponse:
        async def update_cookies_and_request() -> ClientResponse:
            if self.user_session_cookie is not None:
                request.update_cookies(
                    {self._AUTHENTICATION_COOKIE: self.user_session_cookie}
                )
            return await handler(request)

        return await update_cookies_and_request()


class MangaDotNetApi(AbstractAsyncContextManager):
    _BASE_URL = "https://mangadot.net"
    _AUTHENTICATION_COOKIE = "ory_kratos_session"
    _TUS_VERSION = "1.0.0"
    _TUS_MAX_UPLOAD_SIZE = 900 * 1024 * 1024

    _NON_RESUMABLE_ERROR: Final[Sequence[int]] = [
        400,
        401,
        403,
        404,
        409,
        413,
        422,
    ]

    _config: Final[ConfigProvider]
    _client: Final[HttpClientProvider]

    @staticmethod
    def _resolve_ptr_table_json(
        table: list[Any], index: int
    ) -> Any | list[Any] | dict[str, Any]:
        if not isinstance(table, list):
            return table

        value = table[index]

        if isinstance(value, dict):
            result = {}
            k: str
            v: int
            for k, v in value.items():
                key = table[int(k.lstrip("_"))]
                value_index = v
                resolved_value = (
                    MangaDotNetApi._resolve_ptr_table_json(table, value_index)
                    if value_index >= 0
                    else None
                )
                result[key] = resolved_value
            return result
        elif isinstance(value, list):
            result = []
            for v in value:
                if v >= 0:
                    result.append(
                        MangaDotNetApi._resolve_ptr_table_json(table, v)
                    )
                else:
                    result.append(None)
            return result
        else:
            return value

    @staticmethod
    def _parse_metadata(metadata: dict[str, Any]) -> str:
        data = []

        for key, value in metadata.items():
            if value is None:
                continue

            if isinstance(value, list):
                data.append(
                    f"{key} {b64encode(bytes(json.dumps(value), 'utf-8')).decode()}"
                )
            elif isinstance(value, bool):
                data.append(
                    f"{key} {b64encode(bytes('1' if value else '0', 'utf-8')).decode()}"
                )
            else:
                data.append(
                    f"{key} {b64encode(bytes(f'{value}', 'utf-8')).decode()}"
                )

        return ",".join(data)

    def __init__(
        self,
        config: ConfigProvider,
    ) -> None:
        self._config = config
        self._client = create_http_client(
            self._BASE_URL,
            middlewares=[
                UserRateLimitMiddleware(),
                ServerRateLimitMiddleware(),
                RateLimitedMiddleware(),
                MangaDotNetLoginMiddleware(config),
                CloudflareMiddleware(),
            ],
        )

    @override
    async def __aenter__(self) -> Self:
        return self

    @override
    async def __aexit__(self, *args) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.close()

    async def login(self, handler: MangaDotNetLoginRequestHandler) -> bool:
        try:
            async with (
                create_browser() as browser,
                await cast(Browser, browser).new_context() as context,
                await context.new_page() as page,
                ClickSolver(
                    framework=FrameworkType.CAMOUFOX, page=page
                ) as solver,
            ):
                response = cast(
                    PlaywrightResponse,
                    await page.goto(f"{self._BASE_URL}/login"),
                )

                if not await solve_cloudflare_captcha_interstitial(
                    solver, page, response
                ):
                    logging.getLogger(__name__).error(
                        "[Camoufox] Failed to solve cloudflare captcha"
                    )
                    return False

                # Prevent ads from redirecting this page.
                await page.evaluate(
                    "localStorage.setItem('lastPopAt', Date.now());"
                )

                while True:
                    username_element = page.locator("#identifier")
                    password_element = page.locator("#password")

                    try:
                        await username_element.wait_for(
                            timeout=5000, state="attached"
                        )
                        await password_element.wait_for(
                            timeout=5000, state="attached"
                        )
                    except TimeoutError:
                        logging.getLogger(__name__).error(
                            "Unable to find username/password field"
                        )
                        return False

                    (
                        username,
                        password,
                    ) = await handler.request_credentials()

                    if username is None or password is None:
                        return False

                    try:
                        await username_element.fill(username, timeout=5000)
                        await password_element.fill(password, timeout=5000)
                    except TimeoutError:
                        logging.getLogger(__name__).error(
                            "Unable to find username/password field"
                        )
                        return False

                    if not await solve_cloudflare_captcha_turnstile(
                        solver,
                        page,
                        'form > button[type="submit"][class~="bg-[var(--primary)]"]:not(:disabled)',
                    ):
                        logging.getLogger(__name__).error(
                            "[Camoufox] Failed to solve cloudflare captcha"
                        )
                        return False

                    submit_button = page.get_by_text("Log in", exact=True)

                    if await submit_button.count() == 0:
                        logging.getLogger(__name__).error(
                            "[Camoufox] Log in button not found"
                        )
                        return False

                    await submit_button.click()

                    async def check_for_alert() -> None:
                        alert = page.locator('div[role="alert"]')

                        while await alert.count() == 0:
                            await sleep(1)

                    async def check_for_logged_in() -> None:
                        username_element = page.locator("#identifier")

                        while await username_element.count() > 0:
                            await sleep(1)

                    task = create_task(check_for_alert())
                    task2 = create_task(check_for_logged_in())

                    await wait(
                        [task, task2], return_when=asyncio.FIRST_COMPLETED
                    )

                    if task.done():
                        task2.cancel()
                        await page.reload()
                        continue

                    if task2.done():
                        task.cancel()
                        break

                while True:
                    second_factor_header = page.get_by_text(
                        "Confirm your second factor"
                    )

                    if await second_factor_header.count() >= 1:
                        otp = await handler.request_otp()

                        if otp is None:
                            return False

                        input = cast(
                            ElementHandle,
                            await page.wait_for_selector(
                                "#aal2-totp", strict=True
                            ),
                        )

                        await input.fill(otp)

                        submit_button = page.get_by_text("Verify", exact=True)

                        if await submit_button.count() == 0:
                            logging.getLogger(__name__).error(
                                "Verify button not found"
                            )
                            return False

                        await submit_button.click()

                        async def check_for_alert() -> None:
                            alert = page.locator('div[role="alert"]')

                            while await alert.count() == 0:
                                await sleep(1)

                        async def check_for_logged_in() -> None:
                            locator = page.locator("#aal2-totp")

                            while await locator.count() > 0:
                                await sleep(1)

                        task = create_task(check_for_alert())
                        task2 = create_task(check_for_logged_in())

                        await wait(
                            [task, task2], return_when=asyncio.FIRST_COMPLETED
                        )

                        if task.done():
                            task2.cancel()
                            continue

                        if task2.done():
                            task.cancel()
                            break
                    else:
                        break

                cookies = await context.cookies(self._BASE_URL)

                for cookie in cookies:
                    if cookie.get("name") == self._AUTHENTICATION_COOKIE:
                        self._config.mangadotnet_user_session = cookie.get(
                            "value"
                        )
                        return True

                logging.getLogger(__name__).error(
                    "[Camoufox] Unable to find the authentication cookie"
                )
                return False
        except Error:
            logging.getLogger(__name__).exception(
                "[Camoufox] Failed to authenticate due to camoufox error"
            )
            return False

    async def logout(self) -> None:
        self._config.mangadotnet_user_session = None

    @retryable_client_method
    async def get_user_profile(self) -> MangaDotNetProfile:
        async with await self._client.get("/api/profile") as response:
            response.raise_for_status()
            return await response.json()

    @retryable_client_method
    async def search_title(self, title: str) -> MangaDotNetSearch:
        async with await self._client.get(
            "/api/search",
            {"search": title, "sortBy": "relevance", "limit": 10},
        ) as response:
            response.raise_for_status()
            return await response.json()

    @retryable_client_method
    async def get_entry_by_id(
        self, mangadotnet_id: int
    ) -> MangaDotNetMangaEntry:
        async with await self._client.get(
            f"/api/manga/{mangadotnet_id}"
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def get_id_by_title(self, titles: str | Iterable[str]) -> int | None:
        if isinstance(titles, str):
            titles = [titles]

        matches = []

        for title in titles:
            json = await self.search_title(title)

            for manga in json.get("manga_list", []):
                manga_id = manga.get("id")

                if manga_id is None:
                    continue

                manga_entry = await self.get_entry_by_id(manga_id)
                target_manga = manga_entry.get("manga")

                if target_manga is None:
                    continue

                match_base = title.casefold()

                for match_target in [
                    target_manga.get("title"),
                    *target_manga.get("alt_titles", []),
                ]:
                    match_target = match_target.casefold()

                    if len(match_target) > 20 and match_target.startswith(
                        match_base[: floor(len(match_base) * 0.75)]
                    ):
                        id = target_manga.get("id")

                        if id is None:
                            continue

                        matches.append(id)
                        break

                    if match_base == match_target:
                        id = target_manga.get("id")

                        if id is None:
                            continue

                        matches.append(id)
                        break

        if len(matches) == 0:
            return None

        count = Counter(matches)
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

    @retryable_client_method
    async def get_chapters_by_id(
        self, id: int
    ) -> Sequence[MangaDotNetChapterList]:
        async with await self._client.get(
            f"/api/manga/{id}/chapters/list"
        ) as response:
            response.raise_for_status()
            return await response.json()

    @retryable_client_method
    async def get_volumes_by_id(
        self, id: int
    ) -> Sequence[MangaDotNetVolumeList]:
        async with await self._client.get(
            f"/api/manga/{id}/volumes"
        ) as response:
            response.raise_for_status()
            return await response.json()

    @retryable_client_method
    async def get_id_from_mangabaka_id(self, mangabaka_id: int) -> int | None:
        async with await self._client.post(
            "/api/manga/fetch-mangabaka",
            json={"url": f"https://mangabaka.org/{mangabaka_id}"},
        ) as response:
            if response.status == 409:
                json: MangaDotNetFetchMangaBaka = await response.json()
                return dict_get_recursive(json, "existing", "id")
            else:
                response.raise_for_status()
                return None

    @retryable_client_method
    async def get_group_ids(self, name: str) -> MangaDotNetGroupList:
        async with await self._client.get(
            "/api/groups/lookup", params={"q": name, "limit": 10}
        ) as response:
            response.raise_for_status()
            return await response.json()

    @retryable_client_method
    async def get_tus_capabilities(self) -> MangaDotNetTusCapabilities:
        async with await self._client.options(
            "/api/tus", headers={"Origin": self._BASE_URL}
        ) as response:
            response.raise_for_status()
            return MangaDotNetTusCapabilities(
                response.headers.get("Tus-Version", self._TUS_VERSION).split(
                    ","
                ),
                int(
                    response.headers.get(
                        "Tus-Max-Size", self._TUS_MAX_UPLOAD_SIZE
                    )
                ),
                response.headers.get(
                    "Tus-Extension", "creation,expiration"
                ).split(","),
            )

    @dataclass(frozen=True)
    class MangaDotNetTusUploadMetadata:
        manga_id: int
        chapter_number: float | None
        volume_number: float | None
        language: str
        chapter_title: str | None
        group_ids: list[int] | None
        scanlator_name: str | None
        upload_type: Literal["chapter", "volume"] | None
        batch_id: str | None
        stitch_spreads: bool | None

        def to_dict(self) -> dict[str, Any]:
            result: dict[str, Any] = {}

            result["manga_id"] = self.manga_id
            result["language"] = self.language

            if self.chapter_number is not None:
                result["chapter_number"] = self.chapter_number

            if self.volume_number is not None:
                result["volume_number"] = self.volume_number

            if self.chapter_title is not None:
                result["chapter_title"] = self.chapter_title

            if self.group_ids is not None:
                result["group_ids"] = self.group_ids

            if self.scanlator_name is not None:
                result["scanlator_name"] = self.scanlator_name

            if self.upload_type is not None:
                result["upload_type"] = self.upload_type

            if self.batch_id is not None:
                result["batch_id"] = self.batch_id

            if self.stitch_spreads is not None:
                result["stitch_spreads"] = self.stitch_spreads

            return result

    @retryable_client_method
    async def prepare_upload(
        self, file_size: int, metadata: MangaDotNetTusUploadMetadata
    ) -> str:
        async with await self._client.post(
            "/api/tus/",
            headers={
                "Tus-Resumable": self._TUS_VERSION,
                "Upload-Length": f"{file_size:d}",
                "Upload-Metadata": self._parse_metadata(metadata.to_dict()),
            },
        ) as response:
            response.raise_for_status()
            return response.headers.get("Location", "")

    @retryable_client_method
    async def get_upload_offset(self, location: str) -> int:
        async with await self._client.head(
            location, headers={"Tus-Resumable": self._TUS_VERSION}
        ) as response:
            response.raise_for_status()
            return int(response.headers.get("Upload-Offset", 0))

    async def upload_file(
        self,
        location: str,
        file: IO[bytes],
        progress: Callable[[int], None],
        max_retry: int = 5,
    ) -> bool:
        offset = await self.get_upload_offset(location)
        need_new_offset = False
        retry = 0
        retry_duration = 5

        while True:
            try:
                if retry > max_retry:
                    return False

                if need_new_offset:
                    offset = await self.get_upload_offset(location)
                    need_new_offset = False

                file.seek(offset)

                data = file.read(self._config.upload_chunk_size)

                if len(data) == 0:
                    break

                async with await self._client.patch(
                    location,
                    headers={
                        "Content-Type": "application/offset+octet-stream",
                        "Tus-Resumable": self._TUS_VERSION,
                        "Upload-Offset": f"{offset}",
                    },
                    data=data,
                ) as response:
                    response.raise_for_status()

                    offset = int(response.headers.get("Upload-Offset", 0))
                    progress(offset)

                    retry = 0
                    retry_duration = 5
            except OSError:
                # Client got disconnected and needed time to recover.
                await sleep(retry_duration)
                retry += 1
                retry_duration *= 2
            except HttpResponseError as error:
                if error.status in self._NON_RESUMABLE_ERROR:
                    raise
                else:
                    # Some error occured but we can probably resume
                    await sleep(retry_duration)
                    retry += 1
                    retry_duration *= 2
            except KeyboardInterrupt, SystemExit:
                return False

        return True

    class MangaDotNetUploadedMangaList(TypedDict):
        total: ReadOnly[int]
        uploads: ReadOnly[
            Sequence[MangaDotNetApi.MangaDotNetUploadedMangaListUpload]
        ]
        pagination: ReadOnly[
            MangaDotNetApi.MangaDotNetUploadedMangaListPagination
        ]

    class MangaDotNetUploadedMangaListUpload(TypedDict):
        id: ReadOnly[int]
        manga_id: ReadOnly[int]
        status: ReadOnly[Literal["pending", "approved", "rejected"]]
        chapter_number: ReadOnly[float | None]
        volume_number: ReadOnly[float | None]
        chapter_title: ReadOnly[str | None]
        language: ReadOnly[str]
        scanlator_name: ReadOnly[str | None]
        type: ReadOnly[Literal["chapter", "volume"]]
        groups: ReadOnly[
            Sequence[MangaDotNetApi.MangaDotNetUploadedMangaListUploadGroup]
        ]

    class MangaDotNetUploadedMangaListUploadGroup(TypedDict):
        id: ReadOnly[int]
        name: ReadOnly[str]

    class MangaDotNetUploadedMangaListPagination(TypedDict):
        page: ReadOnly[int]
        per_page: ReadOnly[int]
        total: ReadOnly[int]
        total_pages: ReadOnly[int]

    @retryable_client_method
    async def get_uploaded_manga(
        self, mangadotnet_id: int, page: int = 1
    ) -> MangaDotNetUploadedMangaList:
        async with await self._client.get(
            "/api/uploads/mine",
            params={"manga_id": mangadotnet_id, "limit": 100, "page": page},
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def create_from_mangabaka(self, mangabaka_id: int) -> int | None:
        @retryable_client_method
        async def fetch_mangabaka(id: int) -> MangaDotNetFetchMangaBaka:
            async with await self._client.post(
                "/api/manga/fetch-mangabaka",
                json={"url": f"https://mangabaka.org/manga/{id}"},
            ) as response:
                response.raise_for_status()
                return await response.json()

        mb_json = await fetch_mangabaka(mangabaka_id)

        def parse_json(data: MangaDotNetFetchMangaBakaData) -> dict[str, str]:
            result = {}

            for key, value in data.items():
                if value is None:
                    continue

                if isinstance(value, str):
                    result[key] = value
                else:
                    result[key] = json.dumps(value, ensure_ascii=False)

            return result

        @retryable_client_method
        async def create_entry(
            json: MangaDotNetFetchMangaBakaData,
        ) -> MangaDotNetCreateFromMangaBakaResponse:
            form_data = FormData(parse_json(json), default_to_multipart=True)
            async with await self._client.post(
                "/api/manga/create-from-mangabaka", data=form_data
            ) as response:
                response.raise_for_status()
                return await response.json()

        entry = await create_entry(dict_get_recursive(mb_json, "data"))
        return dict_get_recursive(entry, "manga", "id")
