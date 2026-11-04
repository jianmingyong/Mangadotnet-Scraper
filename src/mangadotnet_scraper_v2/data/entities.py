from collections.abc import Sequence
from typing import Literal


class SourceMangaEntryEntity:
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
    chapters: Sequence[SourceMangaEntryChapterEntity]


class SourceMangaEntryChapterEntity:
    chapter_id: str
    language: str
    group: str
    type: Literal["chapter", "volume"]
    chapter_number: float | None
    volume_number: float | None
    title: str
    link: str
    uploaded: bool
