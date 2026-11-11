from typing import Final

from .base import DataProvider


class Data:
    _provider: Final[DataProvider]

    def __init__(self, provider: DataProvider) -> None:
        self._provider = provider

    def initialize(self) -> None:
        self._provider.initialize()

    def close(self) -> None:
        self._provider.close()

    def add_source_entry(
        self, source_id: str, manga_id: str, title: str, link: str
    ) -> None:
        """
        Add a new manga series into source_id. Duplicate manga_id will be rejected.
        """
        self._provider.add_source_entry(source_id, manga_id, title, link)

    def delete_source_entry(self, id: int) -> None:
        """
        Remove a manga series from the entry.
        """
        self._provider.delete_source_entry(id)


__all__ = ["Data", "DataProvider"]
