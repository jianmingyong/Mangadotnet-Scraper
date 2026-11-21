from typing import Any, Literal, TypedDict

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
    mangadotnet_id = IntegerField(null=True)
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
            chapters=[Chapter.from_dict(chapter) for chapter in self.chapters],
        )

    def get_chapter(self, target_chapter: Chapter) -> SourceEntryChapter:
        for chapter in self.chapters:
            chapter: SourceEntryChapter

            if (
                chapter["language"] == target_chapter.language
                and chapter["group"] == target_chapter.group
                and chapter["type"] == target_chapter.type
                and (
                    chapter["type"] == "chapter"
                    and chapter["chapter_number"]
                    == target_chapter.chapter_number
                )
                and (
                    chapter["type"] == "volume"
                    and chapter["volume_number"]
                    == target_chapter.volume_number
                )
            ):
                return chapter

        return {
            "id": target_chapter.id,
            "language": target_chapter.language,
            "group": target_chapter.group,
            "type": target_chapter.type,
            "volume_number": target_chapter.volume_number,
            "chapter_number": target_chapter.chapter_number,
            "title": target_chapter.title,
            "link": target_chapter.link,
            "is_uploaded": False,
            "skip_upload": False,
        }


class SourceEntryChapter(TypedDict):
    id: str
    language: str
    group: str
    type: Literal["chapter", "volume"]
    volume_number: float | None
    chapter_number: float | None
    title: str
    link: str
    is_uploaded: bool
    skip_upload: bool
