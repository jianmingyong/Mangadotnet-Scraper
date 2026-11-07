from abc import ABC, abstractmethod
from collections.abc import Sequence

from .entities import SourceMangaEntryEntity


class DataProvider(ABC):
    def initialize(self) -> None:
        pass

    def close(self) -> None:
        pass

    @abstractmethod
    def add_source_entry(
        self, source_id: str, manga_id: str, title: str, link: str
    ) -> None:
        """
        Add a new manga series into source_id. Duplicate manga_id will be rejected.
        """

    @abstractmethod
    def delete_source_entry(self, id: int) -> None: ...

    @abstractmethod
    def get_source_entries(
        self, source_id: str, offset: int = 0, limit: int = -1
    ) -> Sequence[SourceMangaEntryEntity]: ...
