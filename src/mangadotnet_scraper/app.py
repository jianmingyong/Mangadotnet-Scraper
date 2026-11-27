import logging
from asyncio import Semaphore, TaskGroup, sleep
from collections.abc import Mapping, MutableMapping, Sequence
from contextlib import AbstractAsyncContextManager
from io import BytesIO
from time import monotonic
from typing import (
    Final,
    Self,
    cast,
    override,
)
from zipfile import ZIP_DEFLATED, ZipFile

import pillow_jxl  # noqa: F401
import questionary
from PIL import Image
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

from mangadotnet_scraper.camoufox_utils import Browser
from mangadotnet_scraper.config import Config
from mangadotnet_scraper.config.providers import JsonConfig
from mangadotnet_scraper.data import Data, SourceEntry, SourceEntryChapter
from mangadotnet_scraper.data.providers import CySqliteData
from mangadotnet_scraper.mangabaka_api import MangaBakaApi
from mangadotnet_scraper.mangadot_api import (
    MangaDotApi,
    MangaDotLoginRequestHandler,
    MangaDotTusUploadMetadata,
)
from mangadotnet_scraper.network import HttpResponseError
from mangadotnet_scraper.sources import (
    Chapter,
    Manga,
    Page,
    SourceError,
    SourceProvider,
    SourceProviderInterface,
)
from mangadotnet_scraper.sources.providers import *
from mangadotnet_scraper.utilities import is_digit, is_numeric


class LoginHandler(MangaDotLoginRequestHandler):
    _progress: Final[Progress]

    def __init__(self, progress: Progress) -> None:
        self._progress = progress

    @override
    async def request_credentials(self) -> tuple[str | None, str | None]:
        self._progress.stop()

        username = await questionary.text(
            "Please enter MangaDot Username:"
        ).ask_async()

        password = await questionary.password(
            "Please enter MangaDot Password:"
        ).ask_async()

        return username, password

    @override
    async def request_otp(self) -> str | None:
        self._progress.stop()

        otp = await questionary.text(
            "Please enter MangaDot OTP (6 digits):",
            validate=lambda x: len(x) == 6 and is_digit(x),
        ).ask_async()

        return otp


class App(AbstractAsyncContextManager):
    config: Final[Config]
    data: Final[Data]
    browser: Final[Browser]
    sources: Final[SourceProvider]

    mangabaka_api: Final[MangaBakaApi]
    mangadot_api: Final[MangaDotApi]

    def __init__(self) -> None:
        self.config = JsonConfig()
        self.data = CySqliteData()
        self.browser = Browser()
        self.sources = SourceProvider(self.config, self.browser)

        self.mangabaka_api = MangaBakaApi(self.browser)
        self.mangadot_api = MangaDotApi(self.config, self.browser)

    @override
    async def __aenter__(self) -> Self:
        return self

    @override
    async def __aexit__(self, *args) -> None:
        await self.exit()

    async def exit(self) -> None:
        self.config.save()
        self.data.close()
        await self.browser.close()

        await self.mangabaka_api.close()
        await self.mangadot_api.close()

    async def run(self) -> None:
        get_console().rule("MangaDotNet Scraper and Uploader")

        self.config.load()
        self.data.initialize()
        await self.browser.initialize()

        with Progress(
            SpinnerColumn(),
            TextColumn("Checking MangaDotNet Account"),
            transient=True,
        ) as progress:
            progress.add_task("", total=None)

            while True:
                try:
                    await self.mangadot_api.get_user_profile()
                    break
                except HttpResponseError:
                    # User not logged in.
                    if not await self.mangadot_api.login(
                        LoginHandler(progress)
                    ):
                        continue

                    progress.start()

        await self.show_main_menu()

    def generate_choices(self, text: str | None = None) -> Sequence[Choice]:
        return [
            Choice(
                f"{text} {source.name} [{','.join(source.languages)}]"
                if text is not None
                else f"{source.name} [{','.join(source.languages)}]",
                source.source_id,
            )
            for source in self.sources.get_enabled_sources()
        ]

    async def show_main_menu(self) -> None:
        while True:
            selection = await questionary.select(
                "What would you like to do?",
                choices=[
                    Choice("Fetch Listing", 1),
                    Choice("Fetch Listing Details With Mapping", 2),
                    Choice("Fetch Listing Details Without Mapping", 3),
                    Choice("Manual Source Editing", 4),
                    Choice("Upload", 5),
                    Choice("Settings", 6),
                    Choice("Quit", -1),
                ],
                use_shortcuts=True,
            ).ask_async()

            match selection:
                case 1:
                    # Fetch Listing
                    selection = await questionary.select(
                        "Which Source(s) to Fetch Listing",
                        choices=[
                            Choice("All", -1),
                            *self.generate_choices("Fetch"),
                            Choice("Back", -2),
                        ],
                    ).ask_async()

                    if selection is None or selection == -2:
                        continue
                    elif selection == -1:
                        for source in self.sources.get_enabled_sources():
                            async with source:
                                await self.fetch_source_listing(source)
                    else:
                        async with self.sources.get_source(
                            selection
                        ) as source:
                            await self.fetch_source_listing(source)

                case 2:
                    # Fetch Listing Details With Mapping
                    selection = await questionary.select(
                        "Which Source(s) to Fetch Listing Details With Mapping",
                        choices=[
                            Choice("All", -1),
                            *self.generate_choices("Fetch"),
                            Choice("Back", -2),
                        ],
                    ).ask_async()

                    if selection is None or selection == -2:
                        continue
                    elif selection == -1:
                        for source in self.sources.get_enabled_sources():
                            async with source:
                                await self.fetch_source_listing_details(source)
                    else:
                        async with self.sources.get_source(
                            selection
                        ) as source:
                            await self.fetch_source_listing_details(source)

                case 3:
                    # Fetch Listing Details Without Mapping
                    selection = await questionary.select(
                        "Which Source(s) to Fetch Listing Details Without Mapping",
                        choices=[
                            Choice("All", -1),
                            *self.generate_choices("Fetch"),
                            Choice("Back", -2),
                        ],
                    ).ask_async()

                    if selection is None or selection == -2:
                        continue
                    elif selection == -1:
                        for source in self.sources.get_enabled_sources():
                            async with source:
                                await self.fetch_source_listing_details(
                                    source, True
                                )
                    else:
                        async with self.sources.get_source(
                            selection
                        ) as source:
                            await self.fetch_source_listing_details(
                                source, True
                            )

                case 4:
                    # Manual Source Editing
                    while True:
                        selection = await questionary.select(
                            "Select Source to Manual Mapping",
                            choices=[
                                *self.generate_choices(),
                                Choice("Back", -1),
                            ],
                        ).ask_async()

                        if selection is None or selection == -1:
                            break
                        else:
                            async with self.sources.get_source(
                                selection
                            ) as source:
                                await self.manual_source_editing(source)

                case 5:
                    # Upload
                    selection = await questionary.select(
                        "Which Source(s) to Upload",
                        choices=[
                            Choice("All", -1),
                            *self.generate_choices("Upload"),
                            Choice("Back", -2),
                        ],
                    ).ask_async()

                    if selection is None or selection == -2:
                        continue
                    elif selection == -1:
                        for source in self.sources.get_enabled_sources():
                            async with source:
                                await self.upload_chapters(source)
                    else:
                        async with self.sources.get_source(
                            selection
                        ) as source:
                            await self.upload_chapters(source)

                case 6:
                    # Settings
                    await self.show_settings_menu()

                case _:
                    break

    async def fetch_source_listing(
        self, source: SourceProviderInterface
    ) -> None:
        with Progress(
            SpinnerColumn(),
            TextColumn("Fetching {task.description} Listing"),
            transient=True,
        ) as progress:
            progress.add_task(source.name, total=None)

            try:
                new_entries = 0

                async for manga in source.get_manga_list():
                    progress.print(
                        "Adding:",
                        manga.title,
                        markup=False,
                        highlight=False,
                    )
                    result = self.data.add_source_entry(
                        source.source_id, manga.id, manga.title, manga.link
                    )

                    if result:
                        new_entries += 1
                        logging.getLogger(__name__).info(
                            '[%s] Added: "%s" into source entry.',
                            source.source_id,
                            manga.title,
                        )
                    else:
                        logging.getLogger(__name__).info(
                            '[%s] Skipped: "%s" due to conflicting entry in the source entry.',
                            source.source_id,
                            manga.title,
                        )

                progress.print(
                    f"Done fetching {source.name} Listing. New Entries: {new_entries}",
                    markup=False,
                    highlight=False,
                )
            except SourceError:
                progress.print(
                    f"Error fetching {source.name} Listing",
                    markup=False,
                    highlight=False,
                )
                logging.getLogger(__name__).exception(
                    "[%s] Error fetching source listing.", source.source_id
                )

    async def fetch_source_listing_details(
        self, source: SourceProviderInterface, skip_mapping: bool = False
    ) -> None:
        total_progress = Progress(
            TextColumn("Fetching {task.description} Details"),
            BarColumn(bar_width=None),
            MofNCompleteColumn(),
        )

        current_progress = Progress(
            SpinnerColumn(),
            TextColumn("Fetching: {task.description}", markup=False),
        )

        with Live(
            Group(Rule(), total_progress, Rule(), current_progress),
            transient=True,
        ):
            listing = list(
                self.data.get_source_entries(
                    source.source_id, order_by="title"
                )
            )

            total_progress_task_id = total_progress.add_task(
                source.name, total=len(listing)
            )

            semaphore = Semaphore(self.config.fetch_concurrency)

            async def fetch_manga_detail_task(
                entry: SourceEntry,
            ) -> None:
                async with semaphore:
                    task_id = current_progress.add_task(entry.title)

                    try:
                        if (
                            entry.mangadot_id is None
                            and not entry.manual_mapping_override
                            and not skip_mapping
                        ):
                            need_mapping = True
                        else:
                            need_mapping = False

                        manga = await source.get_manga_update(
                            entry.to_manga(), need_mapping
                        )

                        if need_mapping:
                            await self.update_details(entry, manga)

                            if entry.mangabaka_id is None:
                                entry.mangabaka_id = (
                                    await self.mangabaka_api.get_id_by_title(
                                        [manga.title, *manga.alt_titles]
                                    )
                                )

                            if entry.mangadot_id is None:
                                entry.mangadot_id = (
                                    await self.mangadot_api.get_id_by_title(
                                        [manga.title, *manga.alt_titles]
                                    )
                                )

                                if (
                                    entry.mangadot_id is None
                                    and entry.mangabaka_id is not None
                                ):
                                    entry.mangadot_id = await self.mangadot_api.get_id_from_mangabaka_id(
                                        entry.mangabaka_id
                                    )

                                    if entry.mangadot_id is None:
                                        entry.mangadot_id = await self.mangadot_api.create_from_mangabaka(
                                            entry.mangabaka_id
                                        )

                        # Mapping Done, Check chapters now.
                        await self.update_chapters(entry, manga.chapters)

                        self.data.update_source_entry(entry)
                    except Exception:
                        total_progress.print(f"Error fetching {entry.title}")
                        logging.getLogger(__name__).exception(
                            "[%s] Error fetching %s",
                            source.source_id,
                            entry.title,
                        )
                    finally:
                        current_progress.remove_task(task_id)
                        total_progress.advance(total_progress_task_id)

            try:
                async with TaskGroup() as group:
                    for source_entry in listing:
                        group.create_task(
                            fetch_manga_detail_task(source_entry)
                        )

                total_progress.print(
                    f"Done fetching {source.name} Listing Details"
                )
            except* Exception:
                total_progress.print(
                    f"Error fetching {source.name} Listing Details"
                )
                logging.getLogger().exception(
                    f"Error fetching {source.name} Listing Details"
                )

    async def show_settings_menu(self) -> None:
        while True:
            selection = await questionary.select(
                "What would you like to do?",
                choices=[
                    Choice("Configure Sources", 1),
                    Choice("Back", -1),
                ],
                use_shortcuts=True,
            ).ask_async()

            match selection:
                case 1:
                    choices = []

                    for source_id, source in self.sources.get_sources():
                        choices.append(
                            Choice(
                                source.name,
                                source_id,
                                checked=source_id
                                in self.config.enabled_sources,
                                description=f"{source.name} | Languages: {', '.join(source.languages)} | Version: {source.version}",
                            )
                        )

                    selection = await questionary.checkbox(
                        "Choose sources you would like to enable:",
                        choices=choices,
                        use_jk_keys=False,
                        use_search_filter=True,
                        show_description=True,
                    ).ask_async()

                    if selection is not None:
                        self.config.enabled_sources = selection

                case _:
                    break

    async def manual_source_editing(
        self, source: SourceProviderInterface
    ) -> None:
        async def show_initial_menu() -> None:
            while True:
                entries = list(
                    self.data.get_source_entries(source.source_id, "title")
                )

                choices = [
                    Choice(
                        f"[{entry.mangadot_id or 'NULL'}] [{entry.skip_upload}] {entry.title}",
                        entry.rowid,
                    )
                    for entry in entries
                ]

                selection = await questionary.select(
                    f"{source.name} - {len(entries)} Titles | Select title to edit:",
                    choices=[
                        *choices,
                        Choice("Back", -1),
                    ],
                    use_jk_keys=False,
                    use_search_filter=True,
                ).ask_async()

                if selection is None or selection == -1:
                    break
                else:
                    await show_manga_info_menu(selection)

        async def show_manga_info_menu(rowid: int) -> None:
            while True:
                entry = self.data.get_source_entry(rowid)

                get_console().clear()
                get_console().rule("Manual Source Entry Editor")

                print("Manga Id:", entry.manga_id)
                print("Title:", entry.title)
                print("Alt Titles:")

                if entry.alt_titles is None:
                    print("== No alt titles available ==")
                else:
                    for item in entry.alt_titles.splitlines():
                        print(item)

                print("Link:", entry.link)

                print(
                    "MangaBaka Id:",
                    entry.mangabaka_id or "NULL",
                    f"[https://mangabaka.org/{entry.mangabaka_id}]"
                    if entry.mangabaka_id
                    else "",
                )
                print(
                    "MangaDot Id:",
                    entry.mangadot_id or "NULL",
                    f"[https://mangadot.net/manga/{entry.mangadot_id}]"
                    if entry.mangadot_id
                    else "",
                )
                print("Skip Upload:", entry.skip_upload)

                chapters_uploaded = 0

                for chapter in entry.chapters:
                    chapter = SourceEntryChapter.from_dict(chapter)

                    if chapter.is_uploaded:
                        chapters_uploaded += 1

                print(
                    "Chapters:",
                    len(entry.chapters),
                    f"({chapters_uploaded} Uploaded)",
                )

                can_modify = None
                can_upload = None

                if entry.mangadot_id is None:
                    can_upload = "Cannot upload when MangaDot Id is NULL"

                if len(entry.chapters) == 0:
                    can_modify = "No chapter available to modify"
                    can_upload = "No chapter available to upload"

                selection = await questionary.select(
                    "What would you like to do?",
                    choices=[
                        Choice("Update Entry", 1),
                        Choice("Delete Entry", 2),
                        Choice("Update Mapping", 3),
                        Choice("Enable/Disable Upload", 4),
                        Choice("Modify Chapter", 5, disabled=can_modify),
                        Choice("Upload", 6, disabled=can_upload),
                        Choice("Back", -1),
                    ],
                    use_shortcuts=True,
                ).ask_async()

                match selection:
                    case 1:
                        # Update Entry
                        await update_entry(entry)

                    case 2:
                        # Delete Entry
                        self.data.delete_source_entry(rowid)
                        break

                    case 3:
                        # Update Mapping
                        await update_mapping(entry)

                    case 4:
                        # Enable/Disable Upload
                        entry.skip_upload = not entry.skip_upload
                        self.data.update_source_entry(entry)

                    case 5:
                        # Modify Chapter
                        await show_update_chapter_menu(entry)

                    case 6:
                        # Upload
                        await upload(entry)

                    case _:
                        break

        async def update_mapping(entry: SourceEntry) -> None:
            selection = await questionary.select(
                "What would you like to do?",
                choices=[
                    Choice("Try auto mapping", 1),
                    Choice("Manual mapping (via MangaBaka)", 2),
                    Choice("Manual mapping (via MangaDotNet)", 3),
                    Choice("Back", -1),
                ],
                use_shortcuts=True,
            ).ask_async()

            match selection:
                case 1:
                    with Progress(
                        SpinnerColumn(),
                        TextColumn(
                            "Fetching {task.fields[task]}", markup=False
                        ),
                        transient=True,
                    ) as progress:
                        try:
                            task = progress.add_task(
                                "", total=None, task="MangaBaka Entry"
                            )

                            titles = [entry.title]

                            if entry.alt_titles is not None:
                                titles.extend(entry.alt_titles.splitlines())

                            entry.mangabaka_id = (
                                await self.mangabaka_api.get_id_by_title(
                                    titles
                                )
                            )

                            progress.update(task, task="MangaDot Entry")

                            entry.mangadot_id = (
                                await self.mangadot_api.get_id_by_title(titles)
                            )

                            if (
                                entry.mangadot_id is None
                                and entry.mangabaka_id is not None
                            ):
                                entry.mangadot_id = await self.mangadot_api.get_id_from_mangabaka_id(
                                    entry.mangabaka_id
                                )

                                if entry.mangadot_id is None:
                                    entry.mangadot_id = await self.mangadot_api.create_from_mangabaka(
                                        entry.mangabaka_id
                                    )
                        except HttpResponseError:
                            logging.getLogger(__name__).error("Mapping error")

                case 2:
                    while True:
                        id = await questionary.text(
                            "Enter MangaBaka Id (0 to cancel):",
                            default=str(entry.mangabaka_id or ""),
                            validate=is_digit,
                        ).ask_async()

                        if id is None or id == 0:
                            break
                        else:
                            id = int(id)

                        with Progress(
                            SpinnerColumn(),
                            TextColumn(
                                "Fetching {task.fields[task]}", markup=False
                            ),
                            transient=True,
                        ) as progress:
                            task = progress.add_task(
                                "", total=None, task="MangaBaka Entry"
                            )

                            try:
                                await self.mangabaka_api.get_series_by_id(id)
                            except HttpResponseError:
                                logging.getLogger(__name__).error(
                                    "Unable to get mangabaka series"
                                )
                                continue

                            progress.update(task, task="MangaDot Entry")

                            try:
                                entry.mangadot_id = await self.mangadot_api.get_id_from_mangabaka_id(
                                    id
                                )

                                if entry.mangadot_id is None:
                                    entry.mangadot_id = await self.mangadot_api.create_from_mangabaka(
                                        id
                                    )
                            except HttpResponseError:
                                logging.getLogger(__name__).error(
                                    "Unable to create mangadot id"
                                )
                                break

                            entry.manual_mapping_override = True
                            break

                case 3:
                    while True:
                        id = await questionary.text(
                            "Enter MangaDotNet Id (0 to cancel):",
                            default=str(entry.mangadot_id or ""),
                            validate=is_digit,
                        ).ask_async()

                        if id is None or id == 0:
                            break
                        else:
                            id = int(id)

                        with Progress(
                            SpinnerColumn(),
                            TextColumn(
                                "Fetching {task.fields[task]}", markup=False
                            ),
                            transient=True,
                        ) as progress:
                            task = progress.add_task(
                                "", total=None, task="MangaDot Entry"
                            )

                            try:
                                await self.mangadot_api.get_entry_by_id(id)
                                entry.mangadot_id = id
                            except HttpResponseError:
                                logging.getLogger(__name__).error(
                                    "Unable to find mangadot entry"
                                )
                                break

                            entry.manual_mapping_override = True
                            break

                case _:
                    return

            self.data.update_source_entry(entry)

        async def update_entry(entry: SourceEntry) -> None:
            with Progress(
                SpinnerColumn(),
                TextColumn("Updating {task.description}"),
                transient=True,
            ) as progress:
                progress.add_task(entry.title, total=None)

                try:
                    manga = await source.get_manga_update(entry.to_manga())

                    await self.update_details(entry, manga)
                    await self.update_chapters(entry, manga.chapters)

                    self.data.update_source_entry(entry)
                except Exception:
                    logging.getLogger(__name__).error("Unable to update entry")

        async def show_update_chapter_menu(entry: SourceEntry) -> None:
            chapters = [
                SourceEntryChapter.from_dict(chapter)
                for chapter in entry.chapters
            ]

            while True:
                choices = [
                    Choice(
                        f"[{chapter.language}] Vol. {chapter.volume_number or 0} Ch. {chapter.chapter_number or 0} {chapter.title} [{chapter.group}] [Skipped: {chapter.skip_upload}]",
                        chapter,
                    )
                    for chapter in chapters
                ]

                selection = await questionary.select(
                    f"{entry.title} - {len(chapters)} Chapters | Select chapter to edit:",
                    choices=[
                        *choices,
                        Choice("Back", -1),
                    ],
                    use_jk_keys=False,
                    use_search_filter=True,
                ).ask_async()

                if selection is None or selection == -1:
                    entry.chapters = [
                        chapter.to_dict() for chapter in chapters
                    ]
                    self.data.update_source_entry(entry)
                    break
                else:
                    await show_chapter_menu(selection)

        async def show_chapter_menu(chapter: SourceEntryChapter) -> None:
            while True:
                get_console().clear()
                get_console().rule("Manual Source Entry Editor")

                print(
                    f"Language: {chapter.language} [Override: {chapter.override_language}]"
                )
                print(
                    f"Group: {chapter.group} [Override: {chapter.override_group}]"
                )
                print(
                    f"Type: {chapter.type} [Override: {chapter.override_type}]"
                )
                print(
                    f"Volume Number: {chapter.volume_number} [Override: {chapter.override_volume_number}]"
                )
                print(
                    f"Chapter Number: {chapter.chapter_number} [Override: {chapter.override_chapter_number}]"
                )
                print(
                    f"Title: {chapter.title} [Override: {chapter.override_title}]"
                )
                print("Link:", chapter.link)
                print("Is Uploaded:", chapter.is_uploaded)
                print("Skip Upload:", chapter.skip_upload)

                selection = await questionary.select(
                    "What would you like to do?",
                    choices=[
                        # Choice("Update Language", 1),
                        # Choice("Update Group", 2),
                        # Choice("Update Type", 3),
                        Choice("Update Volume", 4),
                        Choice("Update Chapter", 5),
                        Choice("Update Title", 6),
                        Choice("Enable/Disable Upload", 7),
                        Choice("Back", -1),
                    ],
                    use_shortcuts=True,
                ).ask_async()

                match selection:
                    case 4:
                        # Volume
                        selection = await questionary.text(
                            "Enter New Volume Number:",
                            default=str(
                                chapter.override_volume_number
                                or chapter.volume_number
                            ),
                            validate=is_numeric,
                        ).ask_async()

                        selection = float(selection)

                        if selection is None or selection < 0:
                            continue

                        if (
                            (chapter.override_title or chapter.title)
                            == f"Volume {chapter.override_volume_number or chapter.volume_number}".removesuffix(
                                ".0"
                            )
                        ):
                            chapter.override_title = f"Volume {selection}"

                        chapter.override_volume_number = selection

                    case 5:
                        # Chapter
                        selection = await questionary.text(
                            "Enter New Chapter Number:",
                            default=str(
                                chapter.override_chapter_number
                                or chapter.chapter_number
                            ),
                            validate=is_numeric,
                        ).ask_async()

                        selection = float(selection)

                        if selection is None or selection < 0:
                            continue

                        if (
                            (chapter.override_title or chapter.title)
                            == f"Chapter {chapter.override_chapter_number or chapter.chapter_number}".removesuffix(
                                ".0"
                            )
                        ):
                            chapter.override_title = f"Chapter {selection}"

                        chapter.override_chapter_number = selection

                    case 6:
                        # title
                        selection = await questionary.text(
                            "Enter New Title:",
                            default=chapter.override_title or chapter.title,
                        ).ask_async()

                        chapter.override_title = selection

                    case 7:
                        chapter.skip_upload = not chapter.skip_upload

                    case _:
                        break

        async def upload(entry: SourceEntry) -> None:
            current_progress_title = Progress(
                TextColumn("{task.fields[status]} ({task.fields[count]})")
            )

            current_progress = Progress(
                SpinnerColumn(),
                TextColumn(
                    "[{task.fields[chapter]}] {task.fields[status]}",
                    markup=False,
                ),
                BarColumn(),
                TaskProgressColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
            )

            group_id_cache: MutableMapping[str, int] = {}

            with Live(
                Group(
                    Rule(),
                    current_progress_title,
                    Rule(),
                    current_progress,
                ),
                transient=True,
            ):

                async def upload_task(
                    semaphore: Semaphore,
                    entry: SourceEntry,
                    chapter: SourceEntryChapter,
                ) -> None:
                    async with semaphore:
                        match chapter.type:
                            case "chapter":
                                chapter_text = f"{entry.mangadot_id}:{chapter.override_language or chapter.language}:Ch. {chapter.override_chapter_number or chapter.chapter_number}:{chapter.override_group or chapter.group}"

                            case "volume":
                                chapter_text = f"{entry.mangadot_id}:{chapter.override_language or chapter.language}:Vol. {chapter.override_volume_number or chapter.volume_number}:{chapter.override_group or chapter.group}"

                        task_id = current_progress.add_task(
                            "",
                            start=False,
                            total=None,
                            chapter=chapter_text,
                            status="Fetching Manga Pages...",
                        )

                        try:
                            pages = await source.get_page_list(
                                entry.to_manga(), chapter.to_chapter()
                            )

                            if len(pages) == 0:
                                self.log_chapter_error(
                                    "Fetch Failure", entry, chapter
                                )
                                return

                            current_progress.update(
                                task_id,
                                total=len(pages),
                                status="Downloading Image",
                            )

                            zip_buffer = BytesIO()
                            has_error = False

                            with ZipFile(
                                zip_buffer, "a", ZIP_DEFLATED, compresslevel=9
                            ) as zip_file:
                                download_semaphore = Semaphore(
                                    self.config.download_concurrency
                                )

                                async def download_image_task(
                                    page: Page,
                                ) -> None:
                                    async with download_semaphore:
                                        image = await source.download_image(
                                            source.get_image_request(page)
                                        )
                                        image = (
                                            await source.process_page_image(
                                                image, page
                                            )
                                        )

                                        raw_image = Image.open(BytesIO(image))

                                        zip_file.writestr(
                                            f"{page.page:03d}.{raw_image.format}",
                                            image,
                                        )
                                        current_progress.advance(task_id)

                                try:
                                    async with TaskGroup() as group:
                                        for page in pages:
                                            group.create_task(
                                                download_image_task(page)
                                            )
                                except* Exception:  # noqa: BLE001
                                    has_error = True

                            if has_error:
                                self.log_chapter_error(
                                    "Download Failure", entry, chapter
                                )
                                return

                            zip_file_size = zip_buffer.tell()

                            current_progress.update(
                                task_id,
                                completed=0,
                                total=zip_file_size,
                                status="Preparing Upload (1)",
                            )

                            group_id = group_id_cache.get(
                                chapter.override_group or chapter.group
                            )

                            if group_id is None:
                                groups = await self.mangadot_api.get_group_ids(
                                    chapter.override_group or chapter.group
                                )

                                for group in groups.get("groups", []):
                                    if group.get("name") == (
                                        chapter.override_group or chapter.group
                                    ):
                                        group_id = group.get("id")
                                        group_id_cache[
                                            chapter.override_group
                                            or chapter.group
                                        ] = group_id
                                        break

                            if group_id is None:
                                self.log_chapter_error(
                                    "Fetch Group Failure", entry, chapter
                                )
                                return

                            current_progress.update(
                                task_id,
                                completed=0,
                                total=zip_file_size,
                                status="Preparing Upload (2)",
                            )

                            try:
                                location = (
                                    await self.mangadot_api.prepare_upload(
                                        zip_file_size,
                                        MangaDotTusUploadMetadata(
                                            cast(int, entry.mangadot_id),
                                            chapter.override_chapter_number
                                            or chapter.chapter_number,
                                            chapter.override_volume_number
                                            or chapter.volume_number,
                                            chapter.override_language
                                            or chapter.language,
                                            chapter.override_title
                                            or chapter.title,
                                            [group_id],
                                            None,
                                            chapter.override_type
                                            or chapter.type,
                                            None,
                                            False,
                                        ),
                                    )
                                )

                                def callable_progress(current: int) -> None:
                                    current_progress.update(
                                        task_id,
                                        completed=current,
                                        status="Uploading",
                                    )

                                current_progress.start_task(task_id)
                                current_progress.update(
                                    task_id, status="Uploading"
                                )

                                success = await self.mangadot_api.upload_file(
                                    location, zip_buffer, callable_progress
                                )

                                current_progress.stop_task(task_id)
                                current_progress.update(
                                    task_id,
                                    total=None,
                                    status="Verify Upload (0s)",
                                )

                                if not success:
                                    return

                                found = False
                                start_check = monotonic()

                                while True:
                                    uploaded_mangas = await self.mangadot_api.get_uploaded_manga(
                                        cast(int, entry.mangadot_id)
                                    )

                                    for uploaded_manga in uploaded_mangas.get(
                                        "uploads"
                                    ):
                                        if uploaded_manga.get("language") != (
                                            chapter.override_language
                                            or chapter.language
                                        ):
                                            continue

                                        if uploaded_manga.get("type") != (
                                            chapter.override_type
                                            or chapter.type
                                        ):
                                            continue

                                        if uploaded_manga.get(
                                            "type"
                                        ) == "chapter" and uploaded_manga.get(
                                            "chapter_number"
                                        ) != (
                                            chapter.override_chapter_number
                                            or chapter.chapter_number
                                        ):
                                            continue

                                        if uploaded_manga.get(
                                            "type"
                                        ) == "volume" and uploaded_manga.get(
                                            "volume_number"
                                        ) != (
                                            chapter.override_volume_number
                                            or chapter.volume_number
                                        ):
                                            continue

                                        for group in uploaded_manga.get(
                                            "groups", []
                                        ):
                                            if group.get("name") == (
                                                chapter.override_group
                                                or chapter.group
                                            ):
                                                found = True
                                                break

                                        if found:
                                            break

                                    if found:
                                        break

                                    await sleep(1)

                                    duration = monotonic() - start_check

                                    current_progress.update(
                                        task_id,
                                        status=f"Verify Upload ({duration:.0f}s)",
                                    )

                                    if (
                                        duration
                                        > self.config.upload_verify_duration
                                    ):
                                        break

                                if found:
                                    chapter.is_uploaded = True
                                    self.log_chapter_info(
                                        "Upload Success", entry, chapter
                                    )
                                else:
                                    self.log_chapter_info(
                                        "Upload Failure", entry, chapter
                                    )
                            except HttpResponseError as error:
                                if error.status == 409:
                                    self.log_chapter_info(
                                        "Upload Skipped (Already Uploaded)",
                                        entry,
                                        chapter,
                                    )
                                    chapter.is_uploaded = True
                                else:
                                    raise
                        except Exception:  # noqa: BLE001
                            self.log_chapter_exception(
                                "Upload Failure", entry, chapter
                            )
                        finally:
                            current_progress.remove_task(task_id)

                current_progress_title_task = current_progress_title.add_task(
                    "", total=None, status=f"Uploading: {entry.title}", count=0
                )

                upload_semaphore = Semaphore(self.config.upload_concurrency)

                chapters = []

                async with TaskGroup() as group:
                    chapters_to_upload = []

                    for chapter in entry.chapters:
                        chapter = SourceEntryChapter.from_dict(chapter)
                        chapters.append(chapter)

                        if chapter.skip_upload or chapter.is_uploaded:
                            continue

                        if (
                            chapter.type == "chapter"
                            and (
                                chapter.override_chapter_number
                                or chapter.chapter_number
                            )
                            is None
                        ):
                            continue

                        if (
                            chapter.type == "volume"
                            and (
                                chapter.override_volume_number
                                or chapter.volume_number
                            )
                            is None
                        ):
                            continue

                        chapters_to_upload.append(chapter)

                    current_progress_title.update(
                        current_progress_title_task,
                        count=len(chapters_to_upload),
                    )

                    for chapter in chapters_to_upload:
                        group.create_task(
                            upload_task(upload_semaphore, entry, chapter)
                        )

                entry.chapters = [chapter.to_dict() for chapter in chapters]
                self.data.update_source_entry(entry)

        await show_initial_menu()

    async def upload_chapters(self, source: SourceProviderInterface) -> None:
        total_progress = Progress(
            TextColumn("Upload {task.description} Overall"),
            BarColumn(bar_width=None),
            MofNCompleteColumn(),
        )
        current_progress_title = Progress(
            TextColumn("{task.fields[status]} ({task.fields[count]})")
        )

        current_progress = Progress(
            SpinnerColumn(),
            TextColumn(
                "[{task.fields[chapter]}] {task.fields[status]}", markup=False
            ),
            BarColumn(),
            TaskProgressColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
        )

        group_id_cache: MutableMapping[str, int] = {}

        with Live(
            Group(
                Rule(),
                total_progress,
                Rule(),
                current_progress_title,
                current_progress,
            ),
            transient=True,
        ):
            entries_to_upload = []

            for entry in self.data.get_source_entries(source.source_id):
                if entry.mangadot_id is None or entry.mangadot_id == 0:
                    continue

                if entry.skip_upload:
                    continue

                for chapter in entry.chapters:
                    chapter = SourceEntryChapter.from_dict(
                        cast(Mapping, chapter)
                    )
                    if not chapter.skip_upload and not chapter.is_uploaded:
                        entries_to_upload.append(entry)
                        break

            total_progress_task = total_progress.add_task(
                source.name, total=len(entries_to_upload)
            )
            current_progress_title_task = current_progress_title.add_task(
                "", status="", count=0
            )

            for entry in entries_to_upload:

                async def upload_task(
                    semaphore: Semaphore,
                    entry: SourceEntry,
                    chapter: SourceEntryChapter,
                ) -> None:
                    async with semaphore:
                        match chapter.type:
                            case "chapter":
                                chapter_text = f"{entry.mangadot_id}:{chapter.override_language or chapter.language}:Ch. {chapter.override_chapter_number or chapter.chapter_number}:{chapter.override_group or chapter.group}"

                            case "volume":
                                chapter_text = f"{entry.mangadot_id}:{chapter.override_language or chapter.language}:Vol. {chapter.override_volume_number or chapter.volume_number}:{chapter.override_group or chapter.group}"

                        task_id = current_progress.add_task(
                            "",
                            start=False,
                            total=None,
                            chapter=chapter_text,
                            status="Fetching Manga Pages...",
                        )

                        try:
                            pages = await source.get_page_list(
                                entry.to_manga(), chapter.to_chapter()
                            )

                            if len(pages) == 0:
                                self.log_chapter_error(
                                    "Fetch Failure", entry, chapter
                                )
                                return

                            current_progress.update(
                                task_id,
                                total=len(pages),
                                status="Downloading Image",
                            )

                            zip_buffer = BytesIO()
                            has_error = False

                            with ZipFile(
                                zip_buffer, "a", ZIP_DEFLATED, compresslevel=9
                            ) as zip_file:
                                download_semaphore = Semaphore(
                                    self.config.download_concurrency
                                )

                                async def download_image_task(
                                    page: Page,
                                ) -> None:
                                    async with download_semaphore:
                                        image = await source.download_image(
                                            source.get_image_request(page)
                                        )
                                        image = (
                                            await source.process_page_image(
                                                image, page
                                            )
                                        )

                                        raw_image = Image.open(BytesIO(image))

                                        zip_file.writestr(
                                            f"{page.page:03d}.{raw_image.format}",
                                            image,
                                        )
                                        current_progress.advance(task_id)

                                try:
                                    async with TaskGroup() as group:
                                        for page in pages:
                                            group.create_task(
                                                download_image_task(page)
                                            )
                                except* Exception:  # noqa: BLE001
                                    has_error = True

                            if has_error:
                                self.log_chapter_error(
                                    "Download Failure", entry, chapter
                                )
                                return

                            zip_file_size = zip_buffer.tell()

                            current_progress.update(
                                task_id,
                                completed=0,
                                total=zip_file_size,
                                status="Preparing Upload (1)",
                            )

                            group_id = group_id_cache.get(
                                chapter.override_group or chapter.group
                            )

                            if group_id is None:
                                groups = await self.mangadot_api.get_group_ids(
                                    chapter.override_group or chapter.group
                                )

                                for group in groups.get("groups", []):
                                    if group.get("name") == (
                                        chapter.override_group or chapter.group
                                    ):
                                        group_id = group.get("id")
                                        group_id_cache[
                                            chapter.override_group
                                            or chapter.group
                                        ] = group_id
                                        break

                            if group_id is None:
                                self.log_chapter_error(
                                    "Fetch Group Failure", entry, chapter
                                )
                                return

                            current_progress.update(
                                task_id,
                                completed=0,
                                total=zip_file_size,
                                status="Preparing Upload (2)",
                            )

                            try:
                                location = (
                                    await self.mangadot_api.prepare_upload(
                                        zip_file_size,
                                        MangaDotTusUploadMetadata(
                                            cast(int, entry.mangadot_id),
                                            chapter.override_chapter_number
                                            or chapter.chapter_number,
                                            chapter.override_volume_number
                                            or chapter.volume_number,
                                            chapter.override_language
                                            or chapter.language,
                                            chapter.override_title
                                            or chapter.title,
                                            [group_id],
                                            None,
                                            chapter.override_type
                                            or chapter.type,
                                            None,
                                            False,
                                        ),
                                    )
                                )

                                def callable_progress(current: int) -> None:
                                    current_progress.update(
                                        task_id,
                                        completed=current,
                                        status="Uploading",
                                    )

                                current_progress.start_task(task_id)
                                current_progress.update(
                                    task_id, status="Uploading"
                                )

                                success = await self.mangadot_api.upload_file(
                                    location, zip_buffer, callable_progress
                                )

                                current_progress.stop_task(task_id)
                                current_progress.update(
                                    task_id,
                                    total=None,
                                    status="Verify Upload (0s)",
                                )

                                if not success:
                                    return

                                found = False
                                start_check = monotonic()

                                while True:
                                    uploaded_mangas = await self.mangadot_api.get_uploaded_manga(
                                        cast(int, entry.mangadot_id)
                                    )

                                    for uploaded_manga in uploaded_mangas.get(
                                        "uploads"
                                    ):
                                        if uploaded_manga.get("language") != (
                                            chapter.override_language
                                            or chapter.language
                                        ):
                                            continue

                                        if uploaded_manga.get("type") != (
                                            chapter.override_type
                                            or chapter.type
                                        ):
                                            continue

                                        if uploaded_manga.get(
                                            "type"
                                        ) == "chapter" and uploaded_manga.get(
                                            "chapter_number"
                                        ) != (
                                            chapter.override_chapter_number
                                            or chapter.chapter_number
                                        ):
                                            continue

                                        if uploaded_manga.get(
                                            "type"
                                        ) == "volume" and uploaded_manga.get(
                                            "volume_number"
                                        ) != (
                                            chapter.override_volume_number
                                            or chapter.volume_number
                                        ):
                                            continue

                                        for group in uploaded_manga.get(
                                            "groups", []
                                        ):
                                            if group.get("name") == (
                                                chapter.override_group
                                                or chapter.group
                                            ):
                                                found = True
                                                break

                                        if found:
                                            break

                                    if found:
                                        break

                                    await sleep(1)

                                    duration = monotonic() - start_check

                                    current_progress.update(
                                        task_id,
                                        status=f"Verify Upload ({duration:.0f}s)",
                                    )

                                    if (
                                        duration
                                        > self.config.upload_verify_duration
                                    ):
                                        break

                                if found:
                                    chapter.is_uploaded = True
                                    self.log_chapter_info(
                                        "Upload Success", entry, chapter
                                    )
                                else:
                                    self.log_chapter_info(
                                        "Upload Failure", entry, chapter
                                    )
                            except HttpResponseError as error:
                                if error.status == 409:
                                    self.log_chapter_info(
                                        "Upload Skipped (Already Uploaded)",
                                        entry,
                                        chapter,
                                    )
                                    chapter.is_uploaded = True
                                else:
                                    raise
                        except Exception:  # noqa: BLE001
                            self.log_chapter_exception(
                                "Upload Failure", entry, chapter
                            )
                        finally:
                            current_progress.remove_task(task_id)

                current_progress_title.update(
                    current_progress_title_task,
                    status=f"Uploading: {entry.title}",
                    count=0,
                )

                upload_semaphore = Semaphore(self.config.upload_concurrency)

                chapters = []

                async with TaskGroup() as group:
                    chapters_to_upload = []

                    for chapter in entry.chapters:
                        chapter = SourceEntryChapter.from_dict(chapter)
                        chapters.append(chapter)

                        if chapter.skip_upload or chapter.is_uploaded:
                            continue

                        if (
                            chapter.type == "chapter"
                            and (
                                chapter.override_chapter_number
                                or chapter.chapter_number
                            )
                            is None
                        ):
                            continue

                        if (
                            chapter.type == "volume"
                            and (
                                chapter.override_volume_number
                                or chapter.volume_number
                            )
                            is None
                        ):
                            continue

                        chapters_to_upload.append(chapter)

                    current_progress_title.update(
                        current_progress_title_task,
                        count=len(chapters_to_upload),
                    )

                    for chapter in chapters_to_upload:
                        group.create_task(
                            upload_task(upload_semaphore, entry, chapter)
                        )

                entry.chapters = [chapter.to_dict() for chapter in chapters]
                self.data.update_source_entry(entry)

                total_progress.advance(total_progress_task)

            total_progress.print(f"Done upload {source.name}")

    def log_chapter_info(
        self, type: str, manga: SourceEntry, chapter: SourceEntryChapter
    ) -> None:
        match chapter.type:
            case "chapter":
                logging.getLogger(__name__).info(
                    "%s [%s]: %s:%s:%s %s [%s]",
                    type,
                    manga.rowid,
                    manga.mangadot_id,
                    chapter.override_language or chapter.language,
                    chapter.override_chapter_number or chapter.chapter_number,
                    chapter.override_title or chapter.title,
                    chapter.override_group or chapter.group,
                )

            case "volume":
                logging.getLogger(__name__).info(
                    "%s [%s]: %s:%s:%s %s [%s]",
                    type,
                    manga.rowid,
                    manga.mangadot_id,
                    chapter.override_language or chapter.language,
                    chapter.override_volume_number or chapter.volume_number,
                    chapter.override_title or chapter.title,
                    chapter.override_group or chapter.group,
                )

    def log_chapter_error(
        self, type: str, manga: SourceEntry, chapter: SourceEntryChapter
    ) -> None:
        match chapter.type:
            case "chapter":
                logging.getLogger(__name__).error(
                    "%s [%s]: %s:%s:%s %s [%s]",
                    type,
                    manga.rowid,
                    manga.mangadot_id,
                    chapter.override_language or chapter.language,
                    chapter.override_chapter_number or chapter.chapter_number,
                    chapter.override_title or chapter.title,
                    chapter.override_group or chapter.group,
                )

            case "volume":
                logging.getLogger(__name__).error(
                    "%s [%s]: %s:%s:%s %s [%s]",
                    type,
                    manga.rowid,
                    manga.mangadot_id,
                    chapter.override_language or chapter.language,
                    chapter.override_volume_number or chapter.volume_number,
                    chapter.override_title or chapter.title,
                    chapter.override_group or chapter.group,
                )

    def log_chapter_exception(
        self, type: str, manga: SourceEntry, chapter: SourceEntryChapter
    ) -> None:
        match chapter.type:
            case "chapter":
                logging.getLogger(__name__).exception(
                    "%s [%s]: %s:%s:%s %s [%s]",
                    type,
                    manga.rowid,
                    manga.mangadot_id,
                    chapter.override_language or chapter.language,
                    chapter.override_chapter_number or chapter.chapter_number,
                    chapter.override_title or chapter.title,
                    chapter.override_group or chapter.group,
                )

            case "volume":
                logging.getLogger(__name__).exception(
                    "%s [%s]: %s:%s:%s %s [%s]",
                    type,
                    manga.rowid,
                    manga.mangadot_id,
                    chapter.override_language or chapter.language,
                    chapter.override_volume_number or chapter.volume_number,
                    chapter.override_title or chapter.title,
                    chapter.override_group or chapter.group,
                )

    # Section Non UI Functions ----

    async def update_details(self, entry: SourceEntry, manga: Manga) -> None:
        entry.manga_id = manga.id
        entry.title = manga.title
        entry.alt_titles = "\n".join(manga.alt_titles)
        entry.link = manga.link

    async def update_chapters(
        self, entry: SourceEntry, chapters: Sequence[Chapter]
    ) -> None:
        new_chapters = []

        if entry.mangadot_id is None:
            for chapter in chapters:
                new_chapter = entry.get_chapter(chapter)
                new_chapter.is_uploaded = False
                new_chapters.append(new_chapter)
        else:
            mangadotnet_chapters = await self.mangadot_api.get_chapters_by_id(
                entry.mangadot_id
            )

            mangadotnet_volumes = await self.mangadot_api.get_volumes_by_id(
                entry.mangadot_id
            )

            for chapter in chapters:
                new_chapter = entry.get_chapter(chapter)
                found = False

                match new_chapter.override_type or new_chapter.type:
                    case "chapter":
                        for mangadotnet_chapter in mangadotnet_chapters:
                            if mangadotnet_chapter.get("language") != (
                                new_chapter.override_language
                                or new_chapter.language
                            ):
                                continue

                            if mangadotnet_chapter.get("chapter_number") != (
                                new_chapter.override_chapter_number
                                or new_chapter.chapter_number
                            ):
                                continue

                            for group in mangadotnet_chapter.get("groups", []):
                                if group.get("name") == (
                                    new_chapter.override_group
                                    or new_chapter.group
                                ):
                                    found = True
                                    break

                            if found:
                                break

                    case "volume":
                        for mangadotnet_volume in mangadotnet_volumes:
                            if mangadotnet_volume.get("language") != (
                                new_chapter.override_language
                                or new_chapter.language
                            ):
                                continue

                            if mangadotnet_volume.get("volume_number") != (
                                new_chapter.override_volume_number
                                or new_chapter.volume_number
                            ):
                                continue

                            for group in mangadotnet_volume.get("groups", []):
                                if group.get("name") == (
                                    new_chapter.override_group
                                    or new_chapter.group
                                ):
                                    found = True
                                    break

                            if found:
                                break

                new_chapter.is_uploaded = found
                new_chapters.append(new_chapter)

        entry.chapters = [chapter.to_dict() for chapter in new_chapters]
