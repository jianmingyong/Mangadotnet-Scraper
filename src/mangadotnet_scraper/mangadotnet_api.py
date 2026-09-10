import json
from asyncio import sleep
from base64 import b64encode
from collections import Counter
from collections.abc import Callable, Collection, Iterable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from types import TracebackType
from typing import IO, Any, Final, Literal, NotRequired, ReadOnly, Self, TypedDict, cast

from aiohttp import (
    ClientConnectionError,
    ClientError,
    ClientHandlerType,
    ClientRequest,
    ClientResponse,
    ClientResponseError,
    ClientSession,
    FormData,
)
from aiohttp.typedefs import Middleware
from playwright.async_api import Browser, Error, TimeoutError
from playwright_captcha import CaptchaType, ClickSolver, FrameworkType
from playwright_captcha.utils.exceptions import (
    CaptchaApplyingError,
    CaptchaDataDetectionError,
    CaptchaDetectionError,
    CaptchaSolvingError,
)

from mangadotnet_scraper.camoufox_utils import create_browser
from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.network import create_client, retryable_client_session


class UnauthorizedError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class MangaDotNetResponseError(TypedDict):
    success: NotRequired[ReadOnly[Literal[False]]]
    error: str


class MangaDotNetProfile(TypedDict):
    profile: ReadOnly[MangaDotNetProfileData]


class MangaDotNetProfileData(TypedDict):
    id: ReadOnly[str]
    username: ReadOnly[str]
    email: ReadOnly[str]


class MangaDotNetChapterList(TypedDict):
    id: ReadOnly[int]
    chapter_number: ReadOnly[float]
    volume_number: ReadOnly[float | None]
    language: ReadOnly[str]
    groups: Collection[MangaDotNetChapterListGroup]


class MangaDotNetChapterListGroup(TypedDict):
    id: ReadOnly[int]
    name: ReadOnly[str]
    slug: ReadOnly[str]
    is_scanlator: ReadOnly[bool]


class MangaDotNetGroupList(TypedDict):
    success: ReadOnly[Literal[True]]
    groups: Collection[MangaDotNetGroupListData]


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
    genres: ReadOnly[Collection[str]]
    alt_titles: ReadOnly[Collection[str]]
    authors: ReadOnly[str]
    artists: ReadOnly[str]
    year: ReadOnly[int]
    content_rating: ReadOnly[str]
    rating: ReadOnly[float | None]
    tags: ReadOnly[Collection[str]]
    anilist_id: ReadOnly[int | None]
    mangaupdates_id: ReadOnly[str | None]
    mangabaka_id: ReadOnly[int]
    cover_url: ReadOnly[str | None]
    banner_url: ReadOnly[str | None]
    source_url: ReadOnly[str]


class MangaDotNetCreateFromMangaBakaResponse(TypedDict):
    success: ReadOnly[Literal[True]]
    manga: ReadOnly[MangaDotNetCreateFromMangaBakaResponseManga]


class MangaDotNetCreateFromMangaBakaResponseManga(TypedDict):
    id: ReadOnly[int]
    title: ReadOnly[str]


class MangaDotNetLoginMiddleware(Middleware):
    _UNAUTHORIZED_STATUS_CODE = 401
    _AUTHENTICATION_COOKIE = "ory_kratos_session"

    _config: Final[MangaDotNetScraperConfig]
    _mangadotnet_api: Final[MangaDotNetApi]

    def __init__(self, config: MangaDotNetScraperConfig, mangadotnet_api: MangaDotNetApi) -> None:
        self._config = config
        self._mangadotnet_api = mangadotnet_api

    @property
    def _user_session_cookie(self) -> str | None:
        return self._config.mangadotnet_user_session

    @_user_session_cookie.setter
    def _user_session_cookie(self, value: str | None) -> None:
        self._config.mangadotnet_user_session = value

    async def __call__(self, request: ClientRequest, handler: ClientHandlerType) -> ClientResponse:
        async def update_cookies_and_request() -> ClientResponse:
            if self._user_session_cookie is not None:
                request.update_cookies({self._AUTHENTICATION_COOKIE: self._user_session_cookie})
                return await handler(request)
            else:
                return cast(ClientResponse, request.response) if request.response is not None else await handler(request)

        response: ClientResponse = await update_cookies_and_request()

        if response.status == self._UNAUTHORIZED_STATUS_CODE:
            if self._config.mangadotnet_username is None or self._config.mangadotnet_password is None:
                raise UnauthorizedError("Mangadotnet session is invalid and requires authentication")

            try:
                async with (
                    create_browser() as browser,
                    await cast(Browser, browser).new_context() as context,
                ):
                    page = await context.new_page()

                    async with ClickSolver(framework=FrameworkType.CAMOUFOX, page=page) as solver:
                        await page.goto(f"{self._mangadotnet_api._BASE_API_URL}/login", wait_until="domcontentloaded")

                        # Check for cloudflare
                        try:
                            await page.wait_for_selector('input[name="cf-turnstile-response"]', state="hidden")
                            await solver.solve_captcha(
                                captcha_container=page,
                                captcha_type=CaptchaType.CLOUDFLARE_INTERSTITIAL,
                            )
                        except (
                            TimeoutError,
                            CaptchaDetectionError,
                            CaptchaDataDetectionError,
                            CaptchaSolvingError,
                            CaptchaApplyingError,
                        ):
                            pass

                        username_element = await page.wait_for_selector("#identifier", state="attached", strict=True)
                        if username_element is None:
                            raise UnauthorizedError("Unable to find username field")
                        await username_element.type(self._config.mangadotnet_username)

                        password_element = await page.wait_for_selector("#password", state="attached", strict=True)
                        if password_element is None:
                            raise UnauthorizedError("Unable to find password field")
                        await password_element.type(self._config.mangadotnet_password)

                        try:
                            await solver.solve_captcha(
                                captcha_container=page,
                                captcha_type=CaptchaType.CLOUDFLARE_TURNSTILE,
                                expected_content_selector='form > button[type="submit"][class~="bg-[var(--primary)]"]:not(:disabled)',
                            )
                        except (
                            CaptchaDetectionError,
                            CaptchaDataDetectionError,
                            CaptchaSolvingError,
                            CaptchaApplyingError,
                        ):
                            raise UnauthorizedError("Unable to solve CF captcha")

                        submit_button = page.get_by_text("Log in", exact=True)

                        while not page.is_closed() and await submit_button.is_disabled():
                            await sleep(1)

                        await submit_button.click()

                    try:
                        await page.wait_for_url(self._mangadotnet_api._BASE_API_URL, wait_until="commit")
                    except TimeoutError:
                        # login fail because of something...
                        raise UnauthorizedError("Mangadotnet username or password are invalid")

                    cookies = await context.cookies(self._mangadotnet_api._BASE_API_URL)

                    for cookie in cookies:
                        if cookie.get("name") == self._AUTHENTICATION_COOKIE:
                            self._user_session_cookie = cookie.get("value")
                            break

                    response = await update_cookies_and_request()
            except Error as error:
                raise UnauthorizedError(error.message)

        return response


class MangaDotNetApi(AbstractAsyncContextManager):
    _BASE_API_URL = "https://mangadot.net"
    _AUTHENTICATION_COOKIE = "ory_kratos_session"

    _TUS_VERSION = "1.0.0"
    _TUS_MAX_UPLOAD_SIZE = 900 * 1024 * 1024

    _NON_RESUMABLE_ERROR: Final[list[int]] = [400, 401, 403, 404, 409, 413, 422]

    _config: Final[MangaDotNetScraperConfig]
    _session: Final[ClientSession]
    _tus_chunk_size: int

    @staticmethod
    def _resolve_ptr_table_json(table: list[Any], index: int) -> Any | list[Any] | dict[str, Any]:
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
                    MangaDotNetApi._resolve_ptr_table_json(table, value_index) if value_index >= 0 else None
                )
                result[key] = resolved_value
            return result
        elif isinstance(value, list):
            result = []
            for v in value:
                if v >= 0:
                    result.append(MangaDotNetApi._resolve_ptr_table_json(table, v))
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
                data.append(f"{key} {b64encode(bytes(json.dumps(value), 'utf-8')).decode()}")
            elif isinstance(value, bool):
                data.append(f"{key} {b64encode(bytes('1' if value else '0', 'utf-8')).decode()}")
            else:
                data.append(f"{key} {b64encode(bytes(f'{value}', 'utf-8')).decode()}")

        return ",".join(data)

    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        self._config = config
        self._session = create_client(
            self._BASE_API_URL,
            additional_middlewares=[MangaDotNetLoginMiddleware(config, self)],
            headers={"Origin": self._BASE_API_URL},
        )
        self._tus_chunk_size = config.upload_chunk_size

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        await self._session.close()

    @retryable_client_session
    async def get_user_profile(self) -> MangaDotNetProfile | MangaDotNetResponseError:
        async with self._session.get("/api/profile") as response:
            return await response.json()

    @retryable_client_session
    async def get_chapters_by_id(self, ids: int) -> list[MangaDotNetChapterList] | None:
        async with self._session.get(f"/api/manga/{ids}/chapters/list") as response:
            return await response.json() if response.ok else None

    @retryable_client_session
    async def get_id_from_mangabaka_id(self, mangabaka_id: int) -> int | None:
        while True:
            async with self._session.post(
                "/api/manga/fetch-mangabaka", json={"url": f"https://mangabaka.org/{mangabaka_id}"}
            ) as response:
                if response.status == 409:
                    json = await response.json()
                    return json["duplicate"]["id"]
                else:
                    return None

    @retryable_client_session
    async def get_entry_by_id(self, ids: int) -> dict[str, Any] | None:
        async with self._session.get(
            f"/manga/{ids}.data",
            params={"_routes": "pages/MangaDetailPage"},
        ) as response:
            if not response.ok:
                return None

            json_ptr_data = await response.json(content_type="text/x-script")
            json = self._resolve_ptr_table_json(json_ptr_data, 0)

            if isinstance(json, dict) and "pages/MangaDetailPage" in json:
                manga_detail_page = json["pages/MangaDetailPage"]
                if isinstance(manga_detail_page, dict) and "data" in manga_detail_page:
                    return manga_detail_page["data"]

            return None

    async def get_entry_by_title(self, titles: str | Iterable[str]) -> dict[str, Any] | None:
        if isinstance(titles, str):
            titles = [titles]

        matches = []

        for title in titles:
            async with self._session.get(
                "/search.data",
                params={"search": title, "_routes": "pages/SearchPage"},
            ) as response:
                if not response.ok:
                    return None

                json_ptr_data = await response.json(content_type="text/x-script")
                json = self._resolve_ptr_table_json(json_ptr_data, 0)

                if isinstance(json, dict) and "pages/SearchPage" in json:
                    search_page = json["pages/SearchPage"]
                    if isinstance(search_page, dict) and "data" in search_page:
                        data = search_page["data"]
                        if isinstance(data, dict) and "payload" in data:
                            payload = data["payload"]
                            if isinstance(payload, dict) and "manga_list" in payload:
                                manga_list = payload["manga_list"]
                                if isinstance(manga_list, list):
                                    manga_ids = []

                                    for manga in manga_list:
                                        if isinstance(manga, dict) and "id" in manga:
                                            manga_ids.append(manga["id"])

                                    manga_entries = []

                                    for manga_id in manga_ids:
                                        manga_entries.append(await self.get_entry_by_id(manga_id))

                                    for manga_entry in manga_entries:
                                        if isinstance(manga_entry, dict) and "mangaData" in manga_entry:
                                            manga_data = manga_entry["mangaData"]
                                            if isinstance(manga_data, dict) and "manga" in manga_data:
                                                manga = manga_data["manga"]
                                                if (
                                                    isinstance(manga, dict)
                                                    and "title" in manga_data
                                                    and "alt_titles" in manga_data
                                                ) and manga["title"] in titles:
                                                    matches.append(manga_entry)

        if len(matches) == 0:
            return None

        count = Counter(json_data["mangaData"]["manga"]["id"] for json_data in matches)
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
            if json_data["mangaData"]["manga"]["id"] == common_id:
                return json_data

        return None

    @retryable_client_session
    async def get_group_ids(self, name: str) -> MangaDotNetGroupList | MangaDotNetResponseError:
        async with self._session.get("/api/groups/lookup", params={"q": name, "limit": 10}) as response:
            return await response.json()

    @dataclass(frozen=True)
    class MangaDotNetBatchInitRequest:
        manga_id: int
        language: str
        group_ids: list[int] | None
        type: Literal["chapter", "volume"]
        scanlator_name: str | None
        chapters: list[MangaDotNetApi.MangaDotNetBatchInitRequestChapter]

        def to_dict(self) -> dict:
            return {
                "manga_id": self.manga_id,
                "language": self.language,
                "group_ids": self.group_ids,
                "type": self.type,
                "scanlator_name": self.scanlator_name,
                "chapters": [chapter.to_dict() for chapter in self.chapters],
            }

    @dataclass(frozen=True)
    class MangaDotNetBatchInitRequestChapter:
        chapter_number: int | float | None
        volume_number: int | float | None
        chapter_title: str

        def to_dict(self) -> dict:
            return {
                "chapter_number": self.chapter_number,
                "volume_number": self.volume_number,
                "chapter_title": self.chapter_title,
            }

    class MangaDotNetBatchInitResponse(TypedDict):
        success: Literal[True]
        batch_id: str

    @retryable_client_session
    async def start_batch(
        self, request: MangaDotNetBatchInitRequest
    ) -> MangaDotNetBatchInitResponse | MangaDotNetResponseError:
        async with self._session.post("/api/uploads/batch/init", json=request.to_dict()) as response:
            return await response.json()

    class MangaDotNetBatchCompleteResponse(TypedDict):
        success: Literal[True]

    @retryable_client_session
    async def end_batch(self, batch_id: str) -> MangaDotNetBatchCompleteResponse | MangaDotNetResponseError:
        async with self._session.post(f"/api/uploads/batch/{batch_id}/complete") as response:
            return await response.json()

    @dataclass(frozen=True)
    class MangaDotNetTusCapabilities:
        supported_versions: list[str]
        max_file_size: int
        supported_extensions: list[str]

    @retryable_client_session
    async def get_tus_capabilities(self):
        async with self._session.options("/api/tus", headers={"Origin": MangaDotNetApi._BASE_API_URL}) as response:
            response.raise_for_status()
            return self.MangaDotNetTusCapabilities(
                response.headers.get("Tus-Version", self._TUS_VERSION).split(","),
                int(response.headers.get("Tus-Max-Size", self._TUS_MAX_UPLOAD_SIZE)),
                response.headers.get("Tus-Extension", "creation,expiration").split(","),
            )

    @dataclass(frozen=True)
    class MangaDotNetTusUploadMetadata:
        manga_id: int
        chapter_number: int | float | None
        volume_number: int | float | None
        language: str
        chapter_title: str | None
        group_ids: list[int] | None
        group_id: int | None
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

            if self.group_id is not None:
                result["group_id"] = self.group_id

            if self.scanlator_name is not None:
                result["scanlator_name"] = self.scanlator_name

            if self.upload_type is not None:
                result["upload_type"] = self.upload_type

            if self.batch_id is not None:
                result["batch_id"] = self.batch_id

            if self.stitch_spreads is not None:
                result["stitch_spreads"] = self.stitch_spreads

            return result

    @retryable_client_session
    async def prepare_upload(self, file_size: int, metadata: MangaDotNetTusUploadMetadata) -> str:
        async with self._session.post(
            "/api/tus/",
            headers={
                "Referer": f"{self._BASE_API_URL}/upload",
                "Tus-Resumable": self._TUS_VERSION,
                "Upload-Length": f"{file_size:d}",
                "Upload-Metadata": self._parse_metadata(metadata.to_dict()),
            },
        ) as response:
            response.raise_for_status()
            return response.headers.get("Location", "")

    @retryable_client_session
    async def get_upload_offset(self, location: str) -> int:
        async with self._session.head(location, headers={"Tus-Resumable": self._TUS_VERSION}) as response:
            response.raise_for_status()
            return int(response.headers.get("Upload-Offset", 0))

    async def upload_file(self, location: str, file: IO[bytes], progress: Callable[[int], None], max_retry=5):
        offset = await self.get_upload_offset(location)
        need_new_offset = False
        retry = 0
        retry_duration = 2

        while True:
            try:
                if retry > max_retry:
                    return False

                if need_new_offset:
                    offset = await self.get_upload_offset(location)
                    need_new_offset = False

                file.seek(offset)

                data: bytes = file.read(self._tus_chunk_size)

                if len(data) == 0:
                    break

                async with self._session.patch(
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
                    retry_duration = 2
            except ClientError as error:
                if isinstance(error, ClientResponseError):
                    if error.status in self._NON_RESUMABLE_ERROR:
                        raise
                    else:
                        # Some error occured but we can probably resume
                        await sleep(retry_duration)
                        retry += 1
                        retry_duration *= 2
                elif isinstance(error, ClientConnectionError):
                    # Client got disconnected and needed time to recover.
                    await sleep(retry_duration)
                    retry += 1
                    retry_duration *= 2
            except KeyboardInterrupt, SystemExit:
                return False

        return True

    class MangaDotNetUploadedMangaList(TypedDict):
        success: ReadOnly[Literal[True]]
        total: ReadOnly[int]
        uploads: ReadOnly[Collection[MangaDotNetApi.MangaDotNetUploadedMangaListUpload]]
        pagination: ReadOnly[MangaDotNetApi.MangaDotNetUploadedMangaListPagination]

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
        groups: ReadOnly[Collection[MangaDotNetApi.MangaDotNetUploadedMangaListUploadGroup]]

    class MangaDotNetUploadedMangaListUploadGroup(TypedDict):
        id: ReadOnly[int]
        name: ReadOnly[str]

    class MangaDotNetUploadedMangaListPagination(TypedDict):
        page: ReadOnly[int]
        per_page: ReadOnly[int]
        total: ReadOnly[int]
        total_pages: ReadOnly[int]

    @retryable_client_session
    async def get_uploaded_manga(self, ids: int, page: int = 1) -> MangaDotNetUploadedMangaList:
        async with self._session.get(
            "/api/uploads/mine", params={"manga_id": ids, "limit": 100, "page": page}
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def create_from_mangabaka(
        self, mangabaka_id: int
    ) -> MangaDotNetCreateFromMangaBakaResponse | MangaDotNetFetchMangaBakaError | MangaDotNetResponseError:
        @retryable_client_session
        async def fetch_mangabaka(id: int) -> MangaDotNetFetchMangaBaka | MangaDotNetFetchMangaBakaError:
            async with self._session.post(
                "/api/manga/fetch-mangabaka", json={"url": f"https://mangabaka.org/manga/{id}"}
            ) as response:
                return await response.json()

        mb_json = await fetch_mangabaka(mangabaka_id)

        if mb_json["success"] == False:
            return mb_json

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

        @retryable_client_session
        async def create_entry(
            json: MangaDotNetFetchMangaBakaData,
        ) -> MangaDotNetCreateFromMangaBakaResponse | MangaDotNetResponseError:
            form_data = FormData(parse_json(json), default_to_multipart=True)
            async with self._session.post("/api/manga/create-from-mangabaka", data=form_data) as response:
                return await response.json()

        return await create_entry(mb_json["data"])
