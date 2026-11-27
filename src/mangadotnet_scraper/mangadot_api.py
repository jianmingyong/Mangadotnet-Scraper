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
    ElementHandle,
    Error,
    TimeoutError,
)
from playwright.async_api import (
    Response as PlaywrightResponse,
)
from playwright_captcha import ClickSolver, FrameworkType

from mangadotnet_scraper.camoufox_utils import (
    Browser,
    solve_cloudflare_captcha_interstitial,
    solve_cloudflare_captcha_turnstile,
)
from mangadotnet_scraper.config import Config
from mangadotnet_scraper.network import (
    HttpClient,
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


class MangaDotResponseError(TypedDict):
    success: NotRequired[ReadOnly[Literal[False]]]
    error: ReadOnly[str]


class MangaDotProfile(TypedDict):
    profile: ReadOnly[MangaDotProfileData]


class MangaDotProfileData(TypedDict):
    id: ReadOnly[str]
    username: ReadOnly[str]
    email: ReadOnly[str]


class MangaDotSearch(TypedDict):
    manga_list: ReadOnly[Sequence[MangaDotSearchMangaList]]


class MangaDotSearchMangaList(TypedDict):
    id: ReadOnly[int]
    title: ReadOnly[str]


class MangaDotMangaEntry(TypedDict):
    manga: ReadOnly[MangaDotMangaEntryData]


class MangaDotMangaEntryData(TypedDict):
    id: ReadOnly[int]
    title: ReadOnly[str]
    alt_titles: ReadOnly[Sequence[str]]
    mangabaka_id: ReadOnly[int | None]


class MangaDotChapterList(TypedDict):
    id: ReadOnly[int]
    chapter_number: ReadOnly[float | None]
    volume_number: ReadOnly[float | None]
    language: ReadOnly[str]
    groups: ReadOnly[Sequence[MangaDotChapterListGroup]]


class MangaDotChapterListGroup(TypedDict):
    id: ReadOnly[int]
    name: ReadOnly[str]
    slug: ReadOnly[str]
    is_scanlator: ReadOnly[bool]


class MangaDotVolumeList(TypedDict):
    id: ReadOnly[int]
    volume_number: ReadOnly[float]
    language: ReadOnly[str]
    groups: ReadOnly[Sequence[MangaDotChapterListGroup]]


class MangaDotGroupList(TypedDict):
    groups: ReadOnly[Sequence[MangaDotGroupListData]]


class MangaDotGroupListData(TypedDict):
    id: ReadOnly[int]
    name: ReadOnly[str]


class MangaDotFetchMangaBakaError(MangaDotResponseError):
    duplicate: ReadOnly[MangaDotFetchMangaBakaDuplicate]


class MangaDotFetchMangaBakaDuplicate(TypedDict):
    id: ReadOnly[int]
    title: ReadOnly[str]


class MangaDotFetchMangaBaka(TypedDict):
    success: ReadOnly[Literal[True]]
    data: ReadOnly[MangaDotFetchMangaBakaData]


class MangaDotFetchMangaBakaData(TypedDict):
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


class MangaDotCreateFromMangaBakaResponse(TypedDict):
    manga: ReadOnly[MangaDotCreateFromMangaBakaResponseManga]


class MangaDotCreateFromMangaBakaResponseManga(TypedDict):
    id: ReadOnly[int]
    title: ReadOnly[str]


class MangaDotBatchInitResponse(TypedDict):
    success: ReadOnly[Literal[True]]
    batch_id: ReadOnly[str]


class MangaDotBatchCompleteResponse(TypedDict):
    success: ReadOnly[Literal[True]]


@dataclass(frozen=True)
class MangaDotTusCapabilities:
    supported_versions: Sequence[str]
    max_file_size: int
    supported_extensions: Sequence[str]


@dataclass(frozen=True)
class MangaDotTusUploadMetadata:
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


class MangaDotUploadedMangaList(TypedDict):
    total: ReadOnly[int]
    uploads: ReadOnly[Sequence[MangaDotUploadedMangaListUpload]]
    pagination: ReadOnly[MangaDotUploadedMangaListPagination]


class MangaDotUploadedMangaListUpload(TypedDict):
    id: ReadOnly[int]
    manga_id: ReadOnly[int]
    status: ReadOnly[Literal["pending", "approved", "rejected"]]
    chapter_number: ReadOnly[float | None]
    volume_number: ReadOnly[float | None]
    chapter_title: ReadOnly[str | None]
    language: ReadOnly[str]
    scanlator_name: ReadOnly[str | None]
    type: ReadOnly[Literal["chapter", "volume"]]
    groups: ReadOnly[Sequence[MangaDotUploadedMangaListUploadGroup]]


class MangaDotUploadedMangaListUploadGroup(TypedDict):
    id: ReadOnly[int]
    name: ReadOnly[str]


class MangaDotUploadedMangaListPagination(TypedDict):
    page: ReadOnly[int]
    per_page: ReadOnly[int]
    total: ReadOnly[int]
    total_pages: ReadOnly[int]


class MangaDotLoginRequestHandler(ABC):
    @abstractmethod
    async def request_credentials(self) -> tuple[str | None, str | None]: ...

    @abstractmethod
    async def request_otp(self) -> str | None: ...


class MangaDotLoginMiddleware(Middleware):
    _AUTHENTICATION_COOKIE = "ory_kratos_session"

    _config: Final[Config]

    def __init__(
        self,
        config: Config,
    ) -> None:
        self._config = config

    @property
    def user_session_cookie(self) -> str | None:
        return self._config.mangadotnet_user_session

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


class MangaDotApi(AbstractAsyncContextManager):
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

    _config: Final[Config]
    _browser: Final[Browser]
    _client: Final[HttpClient]

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

    def __init__(self, config: Config, browser: Browser) -> None:
        self._config = config
        self._browser = browser
        self._client = create_http_client(
            browser,
            self._BASE_URL,
            middlewares=[
                UserRateLimitMiddleware(),
                ServerRateLimitMiddleware(),
                RateLimitedMiddleware(),
                MangaDotLoginMiddleware(config),
                CloudflareMiddleware(browser),
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

    async def login(self, handler: MangaDotLoginRequestHandler) -> bool:
        try:
            async with (
                await self._browser.get_shared_context_page() as page,
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
                        "Failed to solve cloudflare captcha"
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
                            "Failed to solve cloudflare captcha"
                        )
                        return False

                    submit_button = page.get_by_text("Log in", exact=True)

                    if await submit_button.count() == 0:
                        logging.getLogger(__name__).error(
                            "Log in button not found"
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

                cookies = await page.context.cookies(self._BASE_URL)

                for cookie in cookies:
                    if cookie.get("name") == self._AUTHENTICATION_COOKIE:
                        self._config.mangadotnet_user_session = cookie.get(
                            "value"
                        )
                        return True

                logging.getLogger(__name__).error(
                    "Unable to find the authentication cookie"
                )
                return False
        except Error:
            logging.getLogger(__name__).exception(
                "Failed to authenticate due to camoufox error"
            )
            return False

    async def logout(self) -> None:
        self._config.mangadotnet_user_session = None

    @retryable_client_method
    async def get_user_profile(self) -> MangaDotProfile:
        async with await self._client.get("/api/profile") as response:
            response.raise_for_status()
            return await response.json()

    @retryable_client_method
    async def search_title(self, title: str) -> MangaDotSearch:
        async with await self._client.get(
            "/api/search",
            {"search": title, "sortBy": "relevance", "limit": 10},
        ) as response:
            response.raise_for_status()
            return await response.json()

    @retryable_client_method
    async def get_entry_by_id(self, mangadotnet_id: int) -> MangaDotMangaEntry:
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
                        match_base[: floor(len(match_base) * 0.9)]
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
    ) -> Sequence[MangaDotChapterList]:
        async with await self._client.get(
            f"/api/manga/{id}/chapters/list"
        ) as response:
            response.raise_for_status()
            return await response.json()

    @retryable_client_method
    async def get_volumes_by_id(self, id: int) -> Sequence[MangaDotVolumeList]:
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
            headers={"Origin": self._BASE_URL},
        ) as response:
            if response.status == 409:
                json: MangaDotFetchMangaBaka = await response.json()
                return dict_get_recursive(json, "existing", "id")
            else:
                response.raise_for_status()
                return None

    @retryable_client_method
    async def get_group_ids(self, name: str) -> MangaDotGroupList:
        async with await self._client.get(
            "/api/groups/lookup", params={"q": name, "limit": 10}
        ) as response:
            response.raise_for_status()
            return await response.json()

    @retryable_client_method
    async def get_tus_capabilities(self) -> MangaDotTusCapabilities:
        async with await self._client.options(
            "/api/tus", headers={"Origin": self._BASE_URL}
        ) as response:
            response.raise_for_status()
            return MangaDotTusCapabilities(
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

    @retryable_client_method
    async def prepare_upload(
        self, file_size: int, metadata: MangaDotTusUploadMetadata
    ) -> str:
        async with await self._client.post(
            "/api/tus/",
            headers={
                "Origin": self._BASE_URL,
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
                        "Origin": self._BASE_URL,
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

    @retryable_client_method
    async def get_uploaded_manga(
        self, mangadot_id: int
    ) -> MangaDotUploadedMangaList:
        async with await self._client.get(
            "/api/uploads/mine",
            params={
                "manga_id": mangadot_id,
                "limit": 100,
                "page": 1,
                "sort": "date_desc",
            },
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def create_from_mangabaka(self, mangabaka_id: int) -> int | None:
        @retryable_client_method
        async def fetch_mangabaka(id: int) -> MangaDotFetchMangaBaka:
            async with await self._client.post(
                "/api/manga/fetch-mangabaka",
                json={"url": f"https://mangabaka.org/manga/{id}"},
                headers={"Origin": self._BASE_URL},
            ) as response:
                response.raise_for_status()
                return await response.json()

        mb_json = await fetch_mangabaka(mangabaka_id)

        def parse_json(data: MangaDotFetchMangaBakaData) -> dict[str, str]:
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
            json: MangaDotFetchMangaBakaData,
        ) -> MangaDotCreateFromMangaBakaResponse:
            form_data = FormData(parse_json(json), default_to_multipart=True)
            async with await self._client.post(
                "/api/manga/create-from-mangabaka",
                data=form_data,
                headers={"Origin": self._BASE_URL},
            ) as response:
                response.raise_for_status()
                return await response.json()

        entry = await create_entry(dict_get_recursive(mb_json, "data"))
        return dict_get_recursive(entry, "manga", "id")
