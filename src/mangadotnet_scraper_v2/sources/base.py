from abc import ABC
from collections.abc import AsyncGenerator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal


@dataclass
class Manga:
    id: str
    title: str
    link: str
    alt_titles: Sequence[str] = []
    chapters: Sequence[MangaChapter] = []


@dataclass
class MangaChapter:
    id: str
    language: str
    group: str
    type: Literal["chapter", "volume"]
    chapter_number: float | None
    volume_number: float | None
    title: str
    link: str


@dataclass(frozen=True)
class MangaPage:
    page_number: int
    image_link: str
    context_data: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class MangaImage:
    filename: str
    data: bytes


class BaseSourceProvider(ABC):
    source_id: Final[str]
    display_name: Final[str]
    languages: Final[Sequence[str]]
    version: Final[int]

    def __init__(
        self,
        source_id: str,
        display_name: str,
        languages: Sequence[str] | None,
        version: int,
    ) -> None:
        self.source_id = source_id
        self.display_name = display_name
        self.languages = languages if languages is not None else ["en"]
        self.version = version

    async def initialize(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def fetch_manga_listing(self) -> AsyncGenerator[Manga]:
        raise NotImplementedError()

    async def fetch_manga_detail(
        self,
        manga: Manga,
        need_metadata: bool = True,
        need_chapters: bool = True,
    ) -> Manga:
        raise NotImplementedError()

    async def fetch_manga_pages(
        self, manga: Manga, chapter: MangaChapter
    ) -> Sequence[MangaPage]:
        raise NotImplementedError()

    async def fetch_manga_image(self, page: MangaPage) -> MangaImage:
        raise NotImplementedError()
