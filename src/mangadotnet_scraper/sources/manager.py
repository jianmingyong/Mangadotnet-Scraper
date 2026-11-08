from collections.abc import (
    ItemsView,
    Iterable,
    MutableMapping,
    MutableSequence,
)
from contextlib import AbstractContextManager
from typing import ClassVar, Final, Self

from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.data import MangaDotNetScraperData
from mangadotnet_scraper.sources.base import BaseModule


class ModuleManager(AbstractContextManager):
    _modules: ClassVar[MutableSequence[type[BaseModule]]] = []

    _config: Final[MangaDotNetScraperConfig]
    _data: Final[MangaDotNetScraperData]

    _created_modules: MutableMapping[str, BaseModule]

    def __init__(
        self, config: MangaDotNetScraperConfig, data: MangaDotNetScraperData
    ) -> None:
        self._config = config
        self._data = data
        self._created_modules = {}

    @classmethod
    def register_module(cls, module: type[BaseModule]) -> None:
        cls._modules.append(module)

    def __enter__(self) -> Self:
        self.prepare()
        return self

    def __exit__(self, *args) -> None:
        pass

    def prepare(self):
        for module in self._modules:
            obj = module.create_module(self._config)
            self._created_modules[obj.module_id] = obj

    def get_modules(self) -> ItemsView[str, BaseModule]:
        return self._created_modules.items()

    def get_module(self, id: str) -> BaseModule:
        return self._created_modules[id]

    def get_enabled_modules(self) -> Iterable[BaseModule]:
        for id in self._config.enabled_sources:
            if id in self._created_modules:
                yield self._created_modules[id]
