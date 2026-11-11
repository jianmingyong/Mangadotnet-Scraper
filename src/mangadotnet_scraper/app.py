from contextlib import AbstractAsyncContextManager
from typing import (
    Final,
    Self,
)

from rich import get_console

import mangadotnet_scraper.sources.providers  # noqa: F401
from mangadotnet_scraper.data import Data
from mangadotnet_scraper.data.providers import SqliteDataProvider
from mangadotnet_scraper.service import ServiceCollection, ServiceProvider
from mangadotnet_scraper.sources import SourceProvider

from .config import Config, ConfigProvider
from .config.providers import JsonConfigProvider
from .data import DataProvider


class AppBuilder:
    _services: Final[ServiceCollection]

    def __init__(self) -> None:
        self._services = ServiceCollection()
        self.with_default_providers()

    def with_default_providers(self) -> Self:
        self._services.register(
            JsonConfigProvider("config.json"), ConfigProvider
        )
        self._services.register(Config)

        self._services.register(SqliteDataProvider("data.db"), DataProvider)
        self._services.register(Data)

        return self

    def with_config(self, provider: ConfigProvider) -> Self:
        if not isinstance(provider, ConfigProvider):
            raise TypeError("Provider must implement ConfigProvider")

        self._services.register(provider, ConfigProvider)
        return self

    def with_data(self, provider: DataProvider) -> Self:
        if not isinstance(provider, DataProvider):
            raise TypeError("Provider must implement DataProvider")

        self._services.register(provider, DataProvider)
        return self

    def build_app(self) -> App:
        return App(self._services)


class App(AbstractAsyncContextManager):
    config: Final[Config]
    data: Final[Data]
    sources: Final[SourceProvider]

    def __init__(self, provider: ServiceProvider) -> None:
        self.config = provider.get_required(Config)
        self.data = provider.get_required(Data)
        self.sources = SourceProvider(self.config)

    async def __aexit__(self, *args) -> None:
        await self.exit()

    async def run(self) -> None:
        get_console().rule("MangaDotNet Scraper and Uploader")

        self.config.load()
        self.data.initialize()

        for name, provider in self.sources.get_sources():
            print(name)

    async def exit(self) -> None:
        self.config.save()
        self.data.close()
