from contextlib import AbstractAsyncContextManager
from typing import (
    Final,
    override,
)

import questionary
from questionary import Choice
from rich import get_console

import mangadotnet_scraper.sources.providers  # noqa: F401
from mangadotnet_scraper.data import Data
from mangadotnet_scraper.data.providers import SqliteDataProvider
from mangadotnet_scraper.sources import SourceProvider

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
                case 6:
                    await self.show_settings_menu()

                case _:
                    break

    async def show_settings_menu(self) -> None:
        while True:
            selection = await questionary.select(
                "What would you like to do?",
                choices=[
                    Choice("Configure Sources", 1),
                    Choice("Configure MangaDotNet Account", 2),
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
                    return
