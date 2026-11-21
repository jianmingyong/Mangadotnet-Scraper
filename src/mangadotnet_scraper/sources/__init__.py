from collections.abc import (
    ItemsView,
    Iterable,
    MutableMapping,
    MutableSequence,
)
from typing import ClassVar, Final

from mangadotnet_scraper.camoufox_utils import Browser
from mangadotnet_scraper.config import Config

from .base import (
    BaseSourceProvider,
    Chapter,
    ImageRequest,
    Manga,
    Page,
    SourceError,
    SourceProviderInterface,
)

__all__ = [
    "BaseSourceProvider",
    "Chapter",
    "ImageRequest",
    "Manga",
    "Page",
    "SourceError",
    "SourceProvider",
    "SourceProviderInterface",
]


class SourceProvider:
    _provider: ClassVar[MutableSequence[type[BaseSourceProvider]]] = []

    _config: Final[Config]
    _browser: Final[Browser]
    _created_provider: MutableMapping[str, BaseSourceProvider]

    def __init__(self, config: Config, browser: Browser) -> None:
        self._config = config
        self._browser = browser
        self._created_provider = {}

        for provider in self._provider:
            obj = provider.create_provider(self._config, self._browser)
            self._created_provider[obj.source_id] = obj

    @classmethod
    def register_source(cls, provider: type[BaseSourceProvider]) -> None:
        cls._provider.append(provider)

    def get_sources(self) -> ItemsView[str, SourceProviderInterface]:
        return self._created_provider.items()

    def get_source(self, id: str) -> SourceProviderInterface:
        return self._created_provider[id]

    def get_enabled_sources(self) -> Iterable[SourceProviderInterface]:
        for id in self._config.enabled_sources:
            if id in self._created_provider:
                yield self._created_provider[id]
