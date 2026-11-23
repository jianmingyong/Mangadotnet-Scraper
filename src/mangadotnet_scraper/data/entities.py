from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from peewee import (
    AutoField,
    BooleanField,
    IntegerField,
    JSONField,
    Model,
    TextField,
)

from mangadotnet_scraper.sources import Chapter, Manga

__all__ = ["Source", "SourceEntry", "SourceEntryChapter", "TableVersion"]


def _default_list() -> Any:
    return []


class TableVersion(Model):
    class Meta:
        table_name = "db_version"

    table_name = TextField(primary_key=True)
    version = IntegerField(default=1)


class Source(Model):
    class Meta:
        table_name = "source"

    source_id = TextField(primary_key=True)
    version = IntegerField(default=1)


class SourceEntry(Model):
    class Meta:
        table_name = "source_entry"
        indexes = (
            (("source_id", "manga_id"), True),
            (("source_id", "link"), True),
        )

    rowid = AutoField(primary_key=True)
    source_id = TextField()
    manga_id = TextField()
    title = TextField()
    alt_titles = TextField(null=True)
    link = TextField()
    mangabaka_id = IntegerField(null=True)
    mangadot_id = IntegerField(null=True)
    manual_mapping_override = BooleanField(default=False)
    skip_upload = BooleanField(default=False)
    chapters = JSONField(default=_default_list)

    def to_manga(self) -> Manga:
        return Manga(
            id=self.manga_id,
            title=self.title,
            link=self.link,
            alt_titles=[title for title in self.alt_titles.split("\n")]
            if self.alt_titles is not None
            else [],
            chapters=[
                SourceEntryChapter.from_dict(chapter).to_chapter()
                for chapter in self.chapters
            ],
        )

    def get_chapter(self, target_chapter: Chapter) -> SourceEntryChapter:
        for chapter in self.chapters:
            chapter = SourceEntryChapter.from_dict(chapter)

            if (
                chapter.language == target_chapter.language
                and chapter.group == target_chapter.group
                and (
                    chapter.type == "chapter"
                    and chapter.chapter_number == target_chapter.chapter_number
                )
                or (
                    chapter.type == "volume"
                    and chapter.volume_number == target_chapter.volume_number
                )
            ):
                return chapter

        return SourceEntryChapter(
            id=target_chapter.id,
            language=target_chapter.language,
            group=target_chapter.group,
            type=target_chapter.type,
            volume_number=target_chapter.volume_number,
            chapter_number=target_chapter.chapter_number,
            title=target_chapter.title,
            link=target_chapter.link,
        )


@dataclass
class SourceEntryChapter:
    id: str
    language: str
    group: str
    type: Literal["chapter", "volume"]
    volume_number: float | None
    chapter_number: float | None
    title: str
    link: str
    is_uploaded: bool = False
    skip_upload: bool = False
    override_language: str | None = None
    override_group: str | None = None
    override_type: Literal["chapter", "volume"] | None = None
    override_volume_number: float | None = None
    override_chapter_number: float | None = None
    override_title: str | None = None

    @classmethod
    def from_dict(cls, mapping: Mapping[str, Any]) -> SourceEntryChapter:
        return SourceEntryChapter(
            id=cast(str, mapping.get("id")),
            language=cast(str, mapping.get("language")),
            group=cast(str, mapping.get("group")),
            type=cast(Literal["chapter", "volume"], mapping.get("type")),
            volume_number=mapping.get("volume_number"),
            chapter_number=mapping.get("chapter_number"),
            title=cast(str, mapping.get("title")),
            link=cast(str, mapping.get("link")),
            is_uploaded=mapping.get("is_uploaded", False),
            skip_upload=mapping.get("skip_upload", False),
            override_language=mapping.get("override_language"),
            override_group=mapping.get("override_group"),
            override_type=mapping.get("override_type"),
            override_volume_number=mapping.get("override_volume_number"),
            override_chapter_number=mapping.get("override_chapter_number"),
            override_title=mapping.get("override_title"),
        )

    def to_dict(self) -> Mapping[str, Any]:
        return {
            "id": self.id,
            "language": self.language,
            "group": self.group,
            "type": self.type,
            "volume_number": self.volume_number,
            "chapter_number": self.chapter_number,
            "title": self.title,
            "link": self.link,
            "is_uploaded": self.is_uploaded,
            "skip_upload": self.skip_upload,
            "override_language": self.override_language,
            "override_group": self.override_group,
            "override_type": self.override_type,
            "override_volume_number": self.override_volume_number,
            "override_chapter_number": self.override_chapter_number,
            "override_title": self.override_title,
        }

    def to_chapter(self) -> Chapter:
        return Chapter(
            id=self.id,
            language=self.language,
            group=self.group,
            type=self.type,
            volume_number=self.volume_number,
            chapter_number=self.chapter_number,
            title=self.title,
            link=self.link,
        )
