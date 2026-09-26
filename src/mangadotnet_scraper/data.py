from collections.abc import Collection
from contextlib import AbstractContextManager
from dataclasses import dataclass
from itertools import groupby
from sqlite3 import Connection, Cursor
from sqlite3 import connect as sqlite3_connect
from string.templatelib import Interpolation, Template
from types import TracebackType
from typing import Final, Literal

from mangadotnet_scraper.config import MangaDotNetScraperConfig


@dataclass(frozen=True)
class ModuleManga:
    title: str
    alt_titles: list[str]
    mangabaka_id: int | None
    mangadotnet_id: int | None
    chapters: list[ModuleChapter]


@dataclass
class ModuleChapter:
    language: str
    scanlator_group: str
    type: Literal["chapter", "volume"]
    chapter_number: float | None
    volume_number: float | None
    title: str
    link: str
    chapter_id: str
    uploaded: bool


class MangaDotNetScraperData(AbstractContextManager):
    _config: Final[MangaDotNetScraperConfig]
    _connection: Final[Connection]

    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        self._config = config
        self._connection = sqlite3_connect(config.data_file, autocommit=False)
        self._connection.execute("PRAGMA foreign_keys = 1;")
        self.initialize()

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None:
        self.close()

    def initialize(self) -> None:
        with self._connection as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS db_version
                (
                    table_name  TEXT    NOT NULL PRIMARY KEY,
                    version     INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS module_manga
                (
                    rowid           INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    module_id       TEXT    NOT NULL,
                    manga_id        TEXT    NOT NULL,
                    link            TEXT    NOT NULL,
                    title           TEXT    NOT NULL,
                    alt_titles      TEXT    DEFAULT NULL,
                    mangabaka_id    INTEGER DEFAULT NULL,
                    mangadotnet_id  INTEGER DEFAULT NULL,
                    last_checked    INTEGER DEFAULT NULL,
                    manual_override INTEGER NOT NULL DEFAULT 0,
                    half_chapters   INTEGER NOT NULL DEFAULT 0,
                    CONSTRAINT module_manga_unique_manga_id UNIQUE (module_id, manga_id)
                );

                CREATE INDEX IF NOT EXISTS module_manga_index_title ON module_manga (module_id, title ASC);

                CREATE TABLE IF NOT EXISTS module_chapter
                (
                    manga_rowid     INTEGER NOT NULL,
                    language        TEXT NOT NULL DEFAULT "en",
                    scanlator_group TEXT NOT NULL,
                    type            TEXT NOT NULL DEFAULT "chapter",
                    chapter_number  REAL DEFAULT NULL,
                    volume_number   REAL DEFAULT NULL,
                    title           TEXT NOT NULL,
                    link            TEXT NOT NULL,
                    chapter_id      TEXT NOT NULL,
                    uploaded        INTEGER NOT NULL DEFAULT 0,
                    skip_upload     INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (manga_rowid) REFERENCES module_manga (rowid) ON UPDATE CASCADE ON DELETE CASCADE
                );

                CREATE UNIQUE INDEX IF NOT EXISTS module_chapter_unique_index_chapter ON module_chapter
                (
                    manga_rowid,
                    language,
                    scanlator_group,
                    chapter_number
                ) WHERE type = "chapter";

                CREATE UNIQUE INDEX IF NOT EXISTS module_chapter_unique_index_volume ON module_chapter
                (
                    manga_rowid,
                    language,
                    scanlator_group,
                    volume_number
                ) WHERE type = "volume";

                INSERT OR IGNORE INTO db_version (table_name, version) VALUES ("module_manga", 6), ("module_chapter", 5);
                """
            )

            cursor = connection.execute("SELECT table_name, version FROM db_version;")
            table_version: dict[str, int] = {}

            for table_name, version in cursor:
                table_version[table_name] = version

    def close(self) -> None:
        self._connection.close()

    def _execute(self, sql: Template) -> Cursor:
        query = ""
        values = []

        for t_string in sql:
            if isinstance(t_string, Interpolation):
                if isinstance(t_string.value, Collection) and not isinstance(t_string.value, str):
                    query += ",".join("?" for _ in range(len(t_string.value)))
                    values.extend(t_string.value)
                else:
                    query += "?"
                    values.append(t_string.value)
            else:
                query += t_string

        return self._connection.execute(query, values)

    def add_module_listing(self, module_id: str, manga_id: str, title: str, link: str) -> None:
        with self._connection:
            self._execute(
                t"""
                INSERT INTO module_manga (module_id, manga_id, title, link)
                VALUES ({module_id}, {manga_id}, {title}, {link})
                ON CONFLICT (module_id, manga_id) DO UPDATE SET title = {title}, link = {link};
                """
            )

    def get_module_listing(self, module_id: str, only_old_entries: bool = True) -> tuple[int, Cursor]:
        if only_old_entries:
            count = self._execute(
                t"""
                SELECT COUNT(*)
                FROM module_manga
                WHERE module_id = {module_id} AND (last_checked IS NULL OR last_checked <= strftime('%s', 'now', '-12 hours'));
                """
            )

            cursor = self._execute(
                t"""
                SELECT rowid, manga_id, link, title, mangabaka_id, mangadotnet_id, manual_override
                FROM module_manga
                WHERE module_id = {module_id} AND (last_checked IS NULL OR last_checked <= strftime('%s', 'now', '-12 hours'))
                ORDER BY title;
                """
            )
        else:
            count = self._execute(t"SELECT COUNT(*) FROM module_manga WHERE module_id = {module_id};")

            cursor = self._execute(
                t"""
                SELECT rowid, manga_id, link, title, mangabaka_id, mangadotnet_id, manual_override
                FROM module_manga
                WHERE module_id = {module_id}
                ORDER BY title;
                """
            )

        return count.fetchone()[0], cursor

    def get_module_listing_non_mapped(self, module_id: str) -> tuple[int, Cursor]:
        count = self._execute(
            t"""
            SELECT COUNT(*)
            FROM module_manga
            WHERE module_id = {module_id} AND mangadotnet_id IS NULL;
            """
        )

        cursor = self._execute(
            t"""
            SELECT rowid, manga_id, link, title, alt_titles, mangabaka_id, mangadotnet_id
            FROM module_manga
            WHERE module_id = {module_id} AND mangadotnet_id IS NULL
            ORDER BY rowid;
            """
        )

        return count.fetchone()[0], cursor

    def update_manual_mapping(self, rowid: int, mangabaka_id: int, mangadotnet_id: int) -> None:
        with self._connection:
            self._execute(
                t"""
                UPDATE module_manga
                SET
                    mangabaka_id = {mangabaka_id},
                    mangadotnet_id = {mangadotnet_id},
                    manual_override = 1
                WHERE
                    rowid = {rowid};
                """
            )

    def add_module_manga(self, rowid: int, manga: ModuleManga) -> None:
        with self._connection:
            self._execute(
                t"""
                UPDATE module_manga
                SET
                    title = {manga.title}, 
                    alt_titles = {"\n".join(manga.alt_titles)},
                    mangabaka_id = {manga.mangabaka_id},
                    mangadotnet_id = {manga.mangadotnet_id},
                    last_checked = strftime('%s', 'now')
                WHERE
                    rowid = {rowid};
                """
            )

            for chapter in manga.chapters:
                if chapter.type == "chapter":
                    self._execute(
                        t"""
                        INSERT INTO module_chapter
                        (
                            manga_rowid,
                            language,
                            scanlator_group,
                            type,
                            chapter_number,
                            volume_number,
                            title,
                            link,
                            chapter_id,
                            uploaded
                        ) VALUES (
                            {rowid},
                            {chapter.language},
                            {chapter.scanlator_group},
                            {chapter.type},
                            {chapter.chapter_number},
                            {chapter.volume_number},
                            {chapter.title},
                            {chapter.link},
                            {chapter.chapter_id},
                            {chapter.uploaded}
                        ) ON CONFLICT (
                            manga_rowid,
                            language,
                            scanlator_group,
                            chapter_number
                        ) WHERE type = "chapter" DO UPDATE SET
                            volume_number = {chapter.volume_number},
                            title = {chapter.title},
                            link = {chapter.link},
                            chapter_id = {chapter.chapter_id},
                            uploaded = {chapter.uploaded};
                        """
                    )
                else:
                    self._execute(
                        t"""
                        INSERT INTO module_chapter
                        (
                            manga_rowid,
                            language,
                            scanlator_group,
                            type,
                            chapter_number,
                            volume_number,
                            title,
                            link,
                            chapter_id,
                            uploaded
                        ) VALUES (
                            {rowid},
                            {chapter.language},
                            {chapter.scanlator_group},
                            {chapter.type},
                            {chapter.chapter_number},
                            {chapter.volume_number},
                            {chapter.title},
                            {chapter.link},
                            {chapter.chapter_id},
                            {chapter.uploaded}
                        ) ON CONFLICT (
                            manga_rowid,
                            language,
                            scanlator_group,
                            volume_number
                        ) WHERE type = "volume" DO UPDATE SET
                            title = {chapter.title},
                            link = {chapter.link},
                            chapter_id = {chapter.chapter_id},
                            uploaded = {chapter.uploaded};
                        """
                    )

            for language, language_group in groupby(manga.chapters, lambda x: x.language):
                for scanlator_group, scanlator_group_group in groupby(language_group, lambda x: x.scanlator_group):
                    for type, type_group in groupby(scanlator_group_group, lambda x: x.type):
                        if type == "chapter":
                            chapter_list = [chapter.chapter_number for chapter in type_group]
                            self._execute(
                                t"""
                                DELETE FROM module_chapter
                                WHERE
                                    manga_rowid = {rowid} AND
                                    language = {language} AND
                                    scanlator_group = {scanlator_group} AND
                                    type = {type} AND
                                    chapter_number NOT IN ({chapter_list});
                                """
                            )
                        elif type == "volume":
                            volume_list = [chapter.volume_number for chapter in type_group]
                            self._execute(
                                t"""
                                DELETE FROM module_chapter
                                WHERE
                                    manga_rowid = {rowid} AND
                                    language = {language} AND
                                    scanlator_group = {scanlator_group} AND
                                    type = {type} AND
                                    volume_number NOT IN ({volume_list});
                                """
                            )

    def remove_module_manga(self, rowid: int) -> None:
        with self._connection:
            self._execute(t"DELETE FROM module_manga WHERE rowid = {rowid};")

    def get_non_uploaded_manga(self, module_id: str) -> tuple[int, Cursor]:
        count = self._execute(
            t"""
            SELECT COUNT(*)
            FROM module_manga
            WHERE
                module_id = {module_id} AND
                rowid IN (SELECT DISTINCT manga_rowid FROM module_chapter WHERE uploaded = 0 AND skip_upload = 0) AND
                mangadotnet_id IS NOT NULL;
            """
        )

        return count.fetchone()[0], self._execute(
            t"""
            SELECT rowid, manga_id, link, title, mangadotnet_id
            FROM module_manga
            WHERE
                module_id = {module_id} AND
                rowid IN (SELECT DISTINCT manga_rowid FROM module_chapter WHERE uploaded = 0 AND skip_upload = 0) AND
                mangadotnet_id IS NOT NULL
            ORDER BY module_id, title;
            """
        )

    def get_non_uploaded_chapters(self, manga_rowid: int) -> tuple[int, Cursor]:
        count = self._execute(
            t"""
            SELECT COUNT(*)
            FROM module_chapter
            WHERE manga_rowid = {manga_rowid} AND uploaded = 0 AND skip_upload = 0;
            """
        )

        return count.fetchone()[0], self._execute(
            t"""
            SELECT manga_rowid, language, scanlator_group, type, chapter_number, volume_number, title, link, chapter_id
            FROM module_chapter
            WHERE manga_rowid = {manga_rowid} AND uploaded = 0 AND skip_upload = 0
            ORDER BY language, scanlator_group, chapter_number;
            """
        )

    def mark_chapter_uploaded(
        self,
        manga_rowid: int,
        language: str,
        scanlator_group: str,
        type: str,
        chapter_number: float | None,
        volume_number: float | None,
    ) -> None:
        with self._connection:
            if type == "chapter":
                self._execute(
                    t"""
                    UPDATE module_chapter SET uploaded = 1
                    WHERE
                        manga_rowid = {manga_rowid} AND
                        language = {language} AND
                        scanlator_group = {scanlator_group} AND
                        type = {type} AND
                        chapter_number = {chapter_number};
                    """
                )
            else:
                self._execute(
                    t"""
                    UPDATE module_chapter SET uploaded = 1
                    WHERE
                        manga_rowid = {manga_rowid} AND
                        language = {language} AND
                        scanlator_group = {scanlator_group} AND
                        type = {type} AND
                        volume_number = {volume_number};
                    """
                )
