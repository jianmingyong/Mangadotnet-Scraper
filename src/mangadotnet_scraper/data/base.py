from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Literal

from mangadotnet_scraper.data.entities import SourceEntry


class DataProvider(ABC):
    def initialize(self) -> None:
        pass

    def close(self) -> None:
        pass

    @abstractmethod
    def add_source_entry(
        self, source_id: str, manga_id: str, title: str, link: str
    ) -> bool:
        """
        Add a new manga series into source_id. Duplicate manga_id will be rejected.
        """

    @abstractmethod
    def delete_source_entry(self, id: int) -> None:
        """
        Remove a manga series from the entry.
        """

    @abstractmethod
    def get_source_entries(
        self,
        source_id: str,
        order_by: Literal["rowid", "title"] = "rowid",
        order: Literal["ASC", "DESC"] = "ASC",
    ) -> Iterator[SourceEntry]:
        """
        Get all source entries by source id.
        """

    @abstractmethod
    def update_source_entry(self, entry: SourceEntry) -> None: ...
