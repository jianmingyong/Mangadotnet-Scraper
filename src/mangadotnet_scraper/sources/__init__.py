from collections.abc import (
    ItemsView,
    Iterable,
    MutableMapping,
    MutableSequence,
)
from typing import ClassVar, Final

from mangadotnet_scraper.config import Config

from .base import BaseSourceProvider


class SourceProvider:
    _provider: ClassVar[MutableSequence[type[BaseSourceProvider]]] = []

    _config: Final[Config]
    _created_provider: MutableMapping[str, BaseSourceProvider]

    def __init__(self, config: Config) -> None:
        self._config = config
        self._created_provider = {}

        for provider in self._provider:
            obj = provider.create_provider(self._config)
            self._created_provider[obj.source_id] = obj

    @classmethod
    def register_source(cls, provider: type[BaseSourceProvider]) -> None:
        cls._provider.append(provider)

    def prepare(self):
        for provider in self._provider:
            obj = provider.create_provider(self._config)
            self._created_provider[obj.source_id] = obj

    def get_sources(self) -> ItemsView[str, BaseSourceProvider]:
        return self._created_provider.items()

    def get_source(self, id: str) -> BaseSourceProvider:
        return self._created_provider[id]

    def get_enabled_sources(self) -> Iterable[BaseSourceProvider]:
        for id in self._config.enabled_sources:
            if id in self._created_provider:
                yield self._created_provider[id]


__all__ = ["BaseSourceProvider", "SourceProvider"]
