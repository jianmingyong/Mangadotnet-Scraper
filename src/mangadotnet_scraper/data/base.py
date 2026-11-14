from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal


@dataclass
class SourceEntryEntity:
    rowid: int
    source_id: str
    manga_id: str
    title: str
    alt_titles: Sequence[str]
    link: str
    mangabaka_id: int | None
    mangadotnet_id: int | None
    manual_mapping_override: bool
    skip_upload: bool
    chapters: Sequence[SourceEntryChapterEntity]


@dataclass
class SourceEntryChapterEntity:
    chapter_id: str
    language: str
    group: str
    type: Literal["chapter", "volume"]
    chapter_number: float | None
    volume_number: float | None
    title: str
    link: str
    is_uploaded: bool


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
        Add a new manga series into source_id.
        """

    @abstractmethod
    def delete_source_entry(self, id: int) -> None: ...

    @abstractmethod
    def get_source_entries(
        self,
        source_id: str,
        offset: int = 0,
        limit: int = -1,
        order_by: Literal["rowid", "title"] | None = None,
        order: Literal["ASC", "DESC"] = "ASC",
    ) -> Sequence[SourceEntryEntity]: ...
