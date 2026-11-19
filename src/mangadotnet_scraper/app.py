import logging
from asyncio import Semaphore, TaskGroup
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from typing import (
    Final,
    Self,
    cast,
    override,
)

import questionary
from questionary import Choice
from rich import get_console
from rich.console import Group
from rich.live import Live
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
)
from rich.rule import Rule

import mangadotnet_scraper.sources.providers  # noqa: F401
from mangadotnet_scraper.config import ConfigProvider
from mangadotnet_scraper.data import DataProvider
from mangadotnet_scraper.data.entities import SourceEntry
from mangadotnet_scraper.data.providers import CySqliteDataProvider
from mangadotnet_scraper.mangabaka_api import MangaBakaApi
from mangadotnet_scraper.mangadotnet_api import (
    MangaDotNetApi,
    MangaDotNetLoginRequestHandler,
)
from mangadotnet_scraper.network import HttpResponseError
from mangadotnet_scraper.sources import BaseSourceProvider, SourceProvider
from mangadotnet_scraper.sources.base import Chapter

from .config.providers import JsonConfigProvider


class LoginHandler(MangaDotNetLoginRequestHandler):
    _progress: Final[Progress]

    def __init__(self, progress: Progress) -> None:
        self._progress = progress

    @override
    async def request_credentials(self) -> tuple[str | None, str | None]:
        self._progress.stop()

        username = await questionary.text(
            "Please enter MangaDotNet Username:"
        ).ask_async()

        password = await questionary.password(
            "Please enter MangaDotNet Password:"
        ).ask_async()

        return username, password

    @override
    async def request_otp(self) -> str | None:
        self._progress.stop()

        otp = await questionary.text(
            "Please enter MangaDotNet OTP (6 digits):",
            validate=lambda x: len(x) == 6 and cast(str, x).isnumeric(),
        ).ask_async()

        return otp


class App(AbstractAsyncContextManager):
    config: Final[ConfigProvider]
    data: Final[DataProvider]
    sources: Final[SourceProvider]

    mangabaka_api: Final[MangaBakaApi]
    mangadotnet_api: Final[MangaDotNetApi]

    def __init__(self) -> None:
        self.config = JsonConfigProvider()
        self.data = CySqliteDataProvider()
        self.sources = SourceProvider(self.config)

        self.mangabaka_api = MangaBakaApi()
        self.mangadotnet_api = MangaDotNetApi(self.config)

    @override
    async def __aenter__(self) -> Self:
        return self

    @override
    async def __aexit__(self, *args) -> None:
        await self.exit()

    async def exit(self) -> None:
        self.config.save()
        self.data.close()

        await self.mangabaka_api.close()
        await self.mangadotnet_api.close()

    async def run(self) -> None:
        get_console().rule("MangaDotNet Scraper and Uploader")

        self.config.load()
        self.data.initialize()

        with Progress(
            SpinnerColumn(),
            TextColumn("Checking MangaDotNet Account"),
            transient=True,
        ) as progress:
            progress.add_task("", total=None)

            while True:
                try:
                    await self.mangadotnet_api.get_user_profile()
                    break
                except HttpResponseError:
                    # User not logged in.
                    if not await self.mangadotnet_api.login(
                        LoginHandler(progress)
                    ):
                        continue

                    progress.start()

        await self.show_main_menu()

    def generate_choices(self, text: str) -> Sequence[Choice]:
        return [
            Choice(
                f"{text} {source.name} [{','.join(source.languages)}]",
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
                    Choice(
                        "Manual Source Mapping (Only Unmapped Entries)",
                        5,
                    ),
                    Choice("Manual Source Editing", 7),
                    Choice("Upload", 4),
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

                case 6:
                    # Settings
                    await self.show_settings_menu()

                case _:
                    break

    async def fetch_source_listing(self, source: BaseSourceProvider) -> None:
        with Progress(
            SpinnerColumn(),
            TextColumn("Fetching {task.description} Listing"),
            transient=True,
        ) as progress:
            progress.add_task(source.name, total=None)

            try:
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
                    f"Done fetching {source.name} Listing",
                    markup=False,
                    highlight=False,
                )
            except Exception:
                progress.print(
                    f"Error fetching {source.name} Listing",
                    markup=False,
                    highlight=False,
                )
                logging.getLogger(__name__).exception(
                    "[%s] Error fetching source listing.", source.source_id
                )

    async def fetch_source_listing_details(
        self, source: BaseSourceProvider, skip_mapping: bool = False
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
            listing = [
                *self.data.get_source_entries(
                    source.source_id, order_by="title"
                )
            ]

            total_progress_task_id = total_progress.add_task(
                source.name, total=len(listing)
            )

            semaphore = Semaphore(self.config.fetch_concurrency)

            async def fetch_manga_detail_task(
                source_entry: SourceEntry,
            ) -> None:
                async with semaphore:
                    task_id = current_progress.add_task(source_entry.title)

                    try:
                        if (
                            source_entry.mangadotnet_id is None
                            and not source_entry.manual_mapping_override
                            and not skip_mapping
                        ):
                            need_mapping = True
                        else:
                            need_mapping = False

                        manga = await source.get_manga_update(
                            source_entry.to_manga(), need_mapping
                        )

                        if need_mapping:
                            if source_entry.mangabaka_id is None:
                                source_entry.mangabaka_id = (
                                    await self.mangabaka_api.get_id_by_title(
                                        [manga.title, *manga.alt_titles]
                                    )
                                )

                            if source_entry.mangadotnet_id is None:
                                source_entry.mangadotnet_id = (
                                    await self.mangadotnet_api.get_id_by_title(
                                        [manga.title, *manga.alt_titles]
                                    )
                                )

                                if (
                                    source_entry.mangadotnet_id is None
                                    and source_entry.mangabaka_id is not None
                                ):
                                    source_entry.mangadotnet_id = await self.mangadotnet_api.get_id_from_mangabaka_id(
                                        source_entry.mangabaka_id
                                    )

                                    if source_entry.mangadotnet_id is None:
                                        source_entry.mangadotnet_id = await self.mangadotnet_api.create_from_mangabaka(
                                            source_entry.mangabaka_id
                                        )

                        # Mapping Done, Check chapters now.
                        await self.update_chapters(
                            source_entry, manga.chapters
                        )

                        self.data.update_source_entry(source_entry)
                    except Exception:
                        total_progress.print(
                            f"Error fetching {source_entry.title}"
                        )
                        logging.getLogger(__name__).exception(
                            "[%s] Error fetching %s",
                            source.source_id,
                            source_entry.title,
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

    async def update_chapters(
        self, source_entry: SourceEntry, chapters: Sequence[Chapter]
    ) -> None:
        if source_entry.mangadotnet_id is None:
            return

        new_chapters = []

        mangadotnet_chapters = await self.mangadotnet_api.get_chapters_by_id(
            source_entry.mangadotnet_id
        )

        mangadotnet_volumes = await self.mangadotnet_api.get_volumes_by_id(
            source_entry.mangadotnet_id
        )

        for chapter in chapters:
            new_chapter = source_entry.get_chapter(chapter)
            found = False

            match chapter.type:
                case "chapter":
                    for mangadotnet_chapter in mangadotnet_chapters:
                        if mangadotnet_chapter.get(
                            "language"
                        ) == new_chapter.get(
                            "language"
                        ) and mangadotnet_chapter.get(
                            "chapter_number"
                        ) == new_chapter.get("chapter_number"):
                            for group in mangadotnet_chapter.get("groups", []):
                                if group.get("name") == new_chapter.get(
                                    "group"
                                ):
                                    found = True
                                    break

                        if found:
                            break

                case "volume":
                    for mangadotnet_volume in mangadotnet_volumes:
                        if mangadotnet_volume.get(
                            "language"
                        ) == new_chapter.get(
                            "language"
                        ) and mangadotnet_volume.get(
                            "volume_number"
                        ) == new_chapter.get("volume_number"):
                            for group in mangadotnet_volume.get("groups", []):
                                if group.get("name") == new_chapter.get(
                                    "group"
                                ):
                                    found = True
                                    break

                        if found:
                            break

            new_chapter["is_uploaded"] = found
            new_chapters.append(new_chapter)

        source_entry.chapters = new_chapters

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
