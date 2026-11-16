from collections.abc import Sequence
from typing import Final, Literal

from mangadotnet_scraper.data.base import SourceEntryEntity

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
    ) -> bool:
        """
        Add a new manga series into source_id. Duplicate manga_id will be rejected.
        """
        return self._provider.add_source_entry(
            source_id, manga_id, title, link
        )

    def delete_source_entry(self, id: int) -> None:
        """
        Remove a manga series from the entry.
        """
        self._provider.delete_source_entry(id)

    def get_source_entries(
        self,
        source_id: str,
        offset: int = 0,
        limit: int = -1,
        order_by: Literal["rowid", "title"] | None = None,
        order: Literal["ASC", "DESC"] = "ASC",
    ) -> Sequence[SourceEntryEntity]:
        return self._provider.get_source_entries(
            source_id, offset, limit, order_by, order
        )


__all__ = ["Data", "DataProvider"]
