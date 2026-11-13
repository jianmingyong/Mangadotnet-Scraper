import logging
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from typing import (
    Final,
    override,
)

import questionary
from questionary import Choice
from rich import get_console
from rich.progress import Progress, SpinnerColumn, TextColumn

import mangadotnet_scraper.sources.providers  # noqa: F401
from mangadotnet_scraper.data import Data
from mangadotnet_scraper.data.providers import SqliteDataProvider
from mangadotnet_scraper.sources import BaseSourceProvider, SourceProvider

from .config import Config
from .config.providers import JsonConfigProvider


class App(AbstractAsyncContextManager):
    config: Final[Config]
    data: Final[Data]
    sources: Final[SourceProvider]

    def __init__(self) -> None:
        self.config = Config(JsonConfigProvider())
        self.data = Data(SqliteDataProvider())
        self.sources = SourceProvider(self.config)

    @override
    async def __aexit__(self, *args) -> None:
        await self.exit()

    async def exit(self) -> None:
        self.config.save()
        self.data.close()

    async def run(self) -> None:
        get_console().rule("MangaDotNet Scraper and Uploader")

        self.config.load()
        self.data.initialize()

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

                case 6:
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
                    self.data.add_source_entry(
                        source.source_id, manga.id, manga.title, manga.link
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
                    f"Error fetching {source.name} Listing"
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
