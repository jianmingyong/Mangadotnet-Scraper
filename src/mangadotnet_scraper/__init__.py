import asyncio
import logging
from asyncio import Semaphore, sleep
from asyncio.taskgroups import TaskGroup
from io import BytesIO
from time import monotonic
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import questionary
from aiohttp import ClientResponseError
from aiohttp.client_exceptions import ClientError
from questionary import Choice
from rich import get_console
from rich.console import Group
from rich.live import Live
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.rule import Rule

from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.data import MangaDotNetScraperData, ModuleChapter, ModuleManga
from mangadotnet_scraper.mangabaka_api import MangaBakaApi
from mangadotnet_scraper.mangadotnet_api import MangaDotNetApi
from mangadotnet_scraper.modules import ArtLapsaModule, BaseModule, EzMangaModule, MangaPage, RitharScansModule


def initialize() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        filename="mangadotnet_scraper.log",
        encoding="utf-8",
    )

    try:
        asyncio.run(initialize_async())
    except KeyboardInterrupt, SystemExit:
        pass


async def initialize_async() -> None:
    get_console().rule("MangaDotNet Scraper and Uploader")

    config = MangaDotNetScraperConfig()
    config.load_config()

    modules: list[BaseModule] = [ArtLapsaModule(config), RitharScansModule(config), EzMangaModule(config)]

    def generate_choices(text: str, start_index: int = 0) -> list[Choice]:
        return [
            Choice(f"{text} {module.display_name}", start_index + index)
            for index, module in zip(range(len(modules)), modules)
        ]

    try:
        with MangaDotNetScraperData(config) as data:
            while True:
                selection = await questionary.select(
                    "What would you like to do?",
                    choices=[
                        Choice("Fetch Listing", 1),
                        Choice("Fetch Listing Details With Mapping", 2),
                        Choice("Fetch Listing Details Without Mapping", 3),
                        Choice("Upload", 4),
                        Choice("Quit", -1),
                    ],
                ).ask_async()

                if selection == 1:
                    selection = await questionary.select(
                        "Which Module(s) to Fetch Listing",
                        choices=[
                            Choice("All", -1),
                            *generate_choices("Fetch"),
                            Choice("Back", -2),
                        ],
                    ).ask_async()

                    if selection == -1:
                        for module in modules:
                            async with module:
                                await fetch_module_listing(module, data)
                    elif selection < len(modules):
                        async with modules[selection] as module:
                            await fetch_module_listing(module, data)
                    else:
                        continue
                elif selection == 2:
                    selection = await questionary.select(
                        "Which Module(s) to Fetch Listing Details With Mapping",
                        choices=[
                            Choice("All", -1),
                            *generate_choices("Fetch"),
                            Choice("Back", -2),
                        ],
                    ).ask_async()

                    if selection == -1:
                        async with MangaBakaApi() as mangabaka_api, MangaDotNetApi(config) as mangadotnet_api:
                            for module in modules:
                                async with module:
                                    await fetch_module_listing_details(
                                        module, config, data, mangabaka_api, mangadotnet_api, only_old_entries=False
                                    )
                    elif selection < len(modules):
                        async with (
                            MangaBakaApi() as mangabaka_api,
                            MangaDotNetApi(config) as mangadotnet_api,
                            modules[selection] as module,
                        ):
                            await fetch_module_listing_details(
                                module, config, data, mangabaka_api, mangadotnet_api, only_old_entries=False
                            )
                    else:
                        continue
                elif selection == 3:
                    selection = await questionary.select(
                        "Which Module(s) to Fetch Listing Details Without Mapping",
                        choices=[
                            Choice("All", -1),
                            *generate_choices("Fetch"),
                            Choice("Back", -2),
                        ],
                    ).ask_async()

                    if selection == -1:
                        async with MangaBakaApi() as mangabaka_api, MangaDotNetApi(config) as mangadotnet_api:
                            for module in modules:
                                async with module:
                                    await fetch_module_listing_details(
                                        module,
                                        config,
                                        data,
                                        mangabaka_api,
                                        mangadotnet_api,
                                        only_old_entries=False,
                                        skip_mapping=True,
                                    )
                    elif selection < len(modules):
                        async with (
                            MangaBakaApi() as mangabaka_api,
                            MangaDotNetApi(config) as mangadotnet_api,
                            modules[selection] as module,
                        ):
                            await fetch_module_listing_details(
                                module,
                                config,
                                data,
                                mangabaka_api,
                                mangadotnet_api,
                                only_old_entries=False,
                                skip_mapping=True,
                            )
                    else:
                        continue
                elif selection == 4:
                    selection = await questionary.select(
                        "Which Module(s) to Upload",
                        choices=[
                            Choice("All", -1),
                            *generate_choices("Upload"),
                            Choice("Back", -2),
                        ],
                    ).ask_async()

                    if selection == -1:
                        async with MangaDotNetApi(config) as mangadotnet_api:
                            for module in modules:
                                async with module:
                                    await upload_chapters(module, config, data, mangadotnet_api)
                    elif selection < len(modules):
                        async with MangaDotNetApi(config) as mangadotnet_api, modules[selection] as module:
                            await upload_chapters(module, config, data, mangadotnet_api)
                    else:
                        continue
                else:
                    break
    finally:
        config.save_config()


async def fetch_module_listing(module: BaseModule, data: MangaDotNetScraperData):
    with Progress(SpinnerColumn(), TextColumn("Fetching {task.description} Listing"), transient=True) as progress:
        progress.add_task(module.display_name, total=None)

        try:
            async for title, link in module.fetch_manga_listing():
                progress.print("Adding:", title, markup=False, highlight=False)
                data.add_module_listing(module.module_id, title, link)

            progress.print(f"Done fetching {module.display_name} Listing")
        except ClientError:
            progress.print(f"Error fetching {module.display_name} Listing")


async def fetch_module_listing_details(
    module: BaseModule,
    config: MangaDotNetScraperConfig,
    data: MangaDotNetScraperData,
    mangabaka_api: MangaBakaApi,
    mangadotnet_api: MangaDotNetApi,
    only_old_entries: bool = True,
    map_only_null: bool = True,
    skip_mapping: bool = False,
) -> None:
    total_progress = Progress(
        TextColumn("Fetching {task.description} Details"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
    )

    current_progress = Progress(SpinnerColumn(), TextColumn("Fetching: {task.description}"))

    with Live(Group(total_progress, Rule(), current_progress), transient=True):
        listing_count, listing = data.get_module_listing(module.module_id, only_old_entries)
        total_progress_task_id = total_progress.add_task(module.display_name, total=listing_count)

        semaphore = Semaphore(config.fetch_concurrency)

        async def fetch_manga_detail_task(
            rowid: int,
            link: str,
            title: str,
            mangabaka_id: int | None,
            mangadotnet_id: int | None,
            manual_override: bool,
        ) -> None:
            async with semaphore:
                task_id = current_progress.add_task(title)

                try:
                    detail = await module.fetch_manga_detail(link)

                    chapters: list[ModuleChapter] = []

                    for chapter in detail.chapters:
                        chapters.append(
                            ModuleChapter(
                                chapter.language,
                                chapter.group,
                                chapter.chapter_number,
                                chapter.volume_number,
                                chapter.chapter_title,
                                chapter.link,
                                False,
                            )
                        )

                    if not manual_override and not skip_mapping:
                        if map_only_null:
                            if mangabaka_id is None:
                                mangabaka_entry = await mangabaka_api.get_entry_by_title(
                                    [detail.title, *detail.alt_titles]
                                )

                                if (
                                    mangabaka_entry is not None
                                    and "id" in mangabaka_entry
                                    and isinstance(mangabaka_entry["id"], int)
                                ):
                                    mangabaka_id = mangabaka_entry["id"]

                            if mangadotnet_id is None:
                                if mangabaka_id is not None:
                                    mangadotnet_id = await mangadotnet_api.get_id_by_mangabaka_id(mangabaka_id)
                                else:
                                    mangadotnet_entry = await mangadotnet_api.get_entry_by_title(
                                        [detail.title, *detail.alt_titles]
                                    )
                                    if mangadotnet_entry is not None:
                                        mangadotnet_id = mangadotnet_entry["mangaData"]["manga"]["id"]
                        else:
                            mangabaka_entry = await mangabaka_api.get_entry_by_title([detail.title, *detail.alt_titles])

                            if (
                                mangabaka_entry is not None
                                and "id" in mangabaka_entry
                                and isinstance(mangabaka_entry["id"], int)
                            ):
                                mangabaka_id = mangabaka_entry["id"]

                            if mangabaka_id is not None:
                                mangadotnet_id = await mangadotnet_api.get_id_by_mangabaka_id(mangabaka_id)
                            else:
                                mangadotnet_entry = await mangadotnet_api.get_entry_by_title(
                                    [detail.title, *detail.alt_titles]
                                )
                                if mangadotnet_entry is not None:
                                    mangadotnet_id = mangadotnet_entry["mangaData"]["manga"]["id"]

                    def is_chapter_uploaded(chapter: ModuleChapter, mangadotnet_chapters: list[Any]) -> bool:
                        for mangadotnet_chapter in mangadotnet_chapters:
                            if isinstance(mangadotnet_chapter, dict):
                                language = mangadotnet_chapter.get("language")
                                chapter_number = mangadotnet_chapter.get("chapter_number")

                                if chapter.language == language and chapter.chapter_number == chapter_number:
                                    groups = mangadotnet_chapter.get("groups", [])

                                    for group in groups:
                                        if (
                                            isinstance(group, dict)
                                            and "name" in group
                                            and chapter.scanlator_group == group["name"]
                                        ):
                                            return True

                        return False

                    if mangadotnet_id is not None:
                        mangadotnet_chapters = await mangadotnet_api.get_chapters_by_id(mangadotnet_id)
                        if mangadotnet_chapters is not None:
                            for chapter in chapters:
                                chapter.uploaded = is_chapter_uploaded(chapter, mangadotnet_chapters)

                    module_manga = ModuleManga(detail.title, detail.alt_titles, mangabaka_id, mangadotnet_id, chapters)

                    data.add_module_manga(rowid, module_manga)
                except ClientError:
                    total_progress.print(f"Error fetching {title}")
                finally:
                    current_progress.remove_task(task_id)
                    total_progress.advance(total_progress_task_id)

        async with asyncio.TaskGroup() as group:
            for rowid, link, title, mangabaka_id, mangadotnet_id, manual_override in listing:
                group.create_task(
                    fetch_manga_detail_task(rowid, link, title, mangabaka_id, mangadotnet_id, manual_override)
                )

        total_progress.print(f"Done fetching {module.display_name} Listing Details")


async def upload_chapters(
    module: BaseModule,
    config: MangaDotNetScraperConfig,
    data: MangaDotNetScraperData,
    mangadotnet_api: MangaDotNetApi,
):
    total_progress = Progress(
        TextColumn("Upload {task.description} Overall"), BarColumn(bar_width=None), MofNCompleteColumn()
    )
    current_progress_title = Progress(TextColumn("{task.fields[status]} ({task.fields[count]})"))

    current_progress = Progress(
        SpinnerColumn(),
        TextColumn("[{task.fields[chapter]}] {task.fields[status]}", markup=False),
        BarColumn(),
        TaskProgressColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
    )

    group_id_cache: dict[str, int] = {}

    with Live(Group(total_progress, Rule(), current_progress_title, current_progress), transient=True):
        manga_count, manga = data.get_non_uploaded_manga(module.module_id)
        total_progress_task = total_progress.add_task(module.display_name, total=manga_count)
        current_progress_title_task = current_progress_title.add_task("", status="")

        for rowid, link, title, mangadotnet_id in manga:
            current_progress_title.update(current_progress_title_task, status=f"Uploading: {title}", count=0)

            chapters_count, chapters = data.get_non_uploaded_chapters(rowid)

            current_progress_title.update(current_progress_title_task, count=chapters_count)

            chapters = [
                (manga_rowid, language, scanlator_group, chapter_number, volume_number, chapter_title, link)
                for manga_rowid, language, scanlator_group, chapter_number, volume_number, chapter_title, link in chapters
            ]

            upload_semaphore = Semaphore(config.upload_concurrency)

            async def upload_chapter_task(
                upload_semaphore: Semaphore,
                mangadotnet_id: int,
                manga_rowid: int,
                language: str,
                scanlator_group: str,
                chapter_number: float,
                volume_number: float | None,
                chapter_title: str,
                chapter_link: str,
                manga_link: str,
            ) -> None:
                async with upload_semaphore:
                    task_id = current_progress.add_task(
                        "",
                        start=False,
                        total=None,
                        chapter=f"{language}:{chapter_number}:{scanlator_group}",
                        status="Fetching Manga Pages...",
                    )

                    try:
                        pages = await module.fetch_manga_pages(manga_link, chapter_link)
                        pages_count = len(pages)

                        current_progress.update(task_id, total=pages_count, status="Downloading Image")

                        zip_buffer = BytesIO()
                        has_error = False

                        with ZipFile(zip_buffer, "a", ZIP_DEFLATED, compresslevel=9) as zip_file:
                            download_semaphore = Semaphore(config.download_concurrency)

                            async def download_image_task(page: MangaPage) -> None:
                                async with download_semaphore:
                                    image = await module.fetch_manga_image(page)
                                    zip_file.writestr(image.filename, image.data)
                                    current_progress.advance(task_id)

                            try:
                                async with TaskGroup() as group:
                                    for page in pages:
                                        group.create_task(download_image_task(page))
                            except* ClientError:
                                has_error = True

                        if has_error:
                            return

                        zip_file_size = zip_buffer.tell()

                        current_progress.update(task_id, completed=0, total=zip_file_size, status="Preparing Upload")

                        group_id = group_id_cache.get(scanlator_group)

                        if group_id is None:
                            groups = await mangadotnet_api.get_group_ids(scanlator_group)
                            if groups["success"] == True:
                                for group in groups["groups"]:
                                    if group["name"] == scanlator_group:
                                        group_id = group["id"]
                                        group_id_cache[scanlator_group] = group["id"]
                                        break

                        if group_id is None:
                            return

                        try:
                            location = await mangadotnet_api.prepare_upload(
                                zip_file_size,
                                MangaDotNetApi.MangaDotNetTusUploadMetadata(
                                    mangadotnet_id,
                                    chapter_number,
                                    volume_number,
                                    language,
                                    chapter_title,
                                    [group_id],
                                    None,
                                    None,
                                    "chapter",
                                    None,
                                    None,
                                ),
                            )
                        except ClientResponseError as error:
                            if error.code == 409:
                                data.mark_chapter_uploaded(manga_rowid, language, scanlator_group, chapter_number)
                            return

                        def callable_progress(current):
                            current_progress.update(task_id, completed=current, status="Uploading")

                        current_progress.start_task(task_id)

                        success = await mangadotnet_api.upload_file(location, zip_buffer, callable_progress)

                        logging.getLogger().info(
                            f"Chapter Uploaded: [{mangadotnet_id}] {language}:{chapter_number} {chapter_title} [{group_id}]"
                        )

                        current_progress.stop_task(task_id)
                        current_progress.update(task_id, total=None, status="Verify Upload (0s)")

                        if not success:
                            return

                        found = False
                        start_check = monotonic()

                        while True:
                            uploaded_mangas = await mangadotnet_api.get_uploaded_manga(mangadotnet_id)

                            if uploaded_mangas["success"]:
                                for uploaded_manga in uploaded_mangas["uploads"]:
                                    if (
                                        uploaded_manga["manga_id"] == mangadotnet_id
                                        and uploaded_manga["language"] == language
                                        and uploaded_manga["chapter_number"] is not None
                                        and abs(float(uploaded_manga["chapter_number"]) - chapter_number) < 0.1
                                        and any(
                                            uploaded_group["id"] == group_id
                                            for uploaded_group in uploaded_manga["groups"]
                                        )
                                        and uploaded_manga["type"] == "chapter"
                                        and (
                                            uploaded_manga["status"] == "pending"
                                            or uploaded_manga["status"] == "approved"
                                        )
                                    ):
                                        # Upload Success
                                        found = True
                                        break

                            if found:
                                break

                            await sleep(1)

                            duration = monotonic() - start_check
                            current_progress.update(task_id, status=f"Verify Upload ({duration:.0f}s)")

                            if duration > config.upload_verify_duration:
                                break

                        if found:
                            data.mark_chapter_uploaded(manga_rowid, language, scanlator_group, chapter_number)
                    except ClientError:
                        pass
                    finally:
                        current_progress.remove_task(task_id)

            async with TaskGroup() as group:
                for (
                    manga_rowid,
                    language,
                    scanlator_group,
                    chapter_number,
                    volume_number,
                    chapter_title,
                    chapter_link,
                ) in chapters:
                    group.create_task(
                        upload_chapter_task(
                            upload_semaphore,
                            mangadotnet_id,
                            manga_rowid,
                            language,
                            scanlator_group,
                            chapter_number,
                            volume_number,
                            chapter_title,
                            chapter_link,
                            link,
                        )
                    )

            total_progress.advance(total_progress_task)

        total_progress.print(f"Done upload {module.display_name}")
