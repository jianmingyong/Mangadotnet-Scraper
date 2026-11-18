from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from mangadotnet_scraper.sources.base import Chapter, Manga


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

    def to_manga(self) -> Manga:
        return Manga(
            id=self.manga_id,
            title=self.title,
            link=self.link,
            alt_titles=[title for title in self.alt_titles],
            chapters=[chapter.to_chapter() for chapter in self.chapters],
        )

    def get_chapter(self, target_chapter: Chapter) -> SourceEntryChapterEntity:
        for chapter in self.chapters:
            if (
                chapter.language == target_chapter.language
                and chapter.group == target_chapter.group
                and chapter.type == target_chapter.type
                and (
                    chapter.type == "chapter"
                    and chapter.chapter_number == target_chapter.chapter_number
                )
                and (
                    chapter.type == "volume"
                    and chapter.volume_number == target_chapter.volume_number
                )
            ):
                return chapter

        return SourceEntryChapterEntity(
            chapter_id=target_chapter.id,
            language=target_chapter.language,
            group=target_chapter.group,
            type=target_chapter.type,
            volume_number=target_chapter.volume_number,
            chapter_number=target_chapter.chapter_number,
            title=target_chapter.title,
            link=target_chapter.link,
            is_uploaded=False,
        )


@dataclass
class SourceEntryChapterEntity:
    chapter_id: str
    language: str
    group: str
    type: Literal["chapter", "volume"]
    volume_number: float | None
    chapter_number: float | None
    title: str
    link: str
    is_uploaded: bool

    def to_chapter(self) -> Chapter:
        return Chapter(
            id=self.chapter_id,
            language=self.language,
            group=self.group,
            type=self.type,
            volume_number=self.volume_number,
            chapter_number=self.chapter_number,
            title=self.title,
            link=self.link,
        )
