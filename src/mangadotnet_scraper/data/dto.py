from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal


@dataclass
class MangaDto:
    id: str
    title: str
    alt_titles: Sequence[str]
    link: str
    mangabaka_id: int | None
    mangadotnet_id: int | None
    chapters: Sequence[ChapterDto]


@dataclass
class ChapterDto:
    id: str
    language: str
    group: str
    type: Literal["chapter", "volume"]
    chapter_number: float | None
    volume_number: float | None
    title: str
    link: str
    uploaded: bool
