import sqlite3
from contextlib import AbstractContextManager
from dataclasses import dataclass
from sqlite3 import Cursor
from string.templatelib import Interpolation, Template
from typing import Final

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
    chapter_number: float
    volume_number: float | None
    chapter_title: str
    link: str
    uploaded: bool


class MangaDotNetScraperData(AbstractContextManager):
    _config: Final[MangaDotNetScraperConfig]
    _connection: Final[sqlite3.Connection]

    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        self._config = config
        self._connection = sqlite3.connect("data.db", autocommit=False)
        self.initialize()

    def __exit__(self, _exc_type, _exc_val, _exc_tb) -> None:
        self.close()

    def initialize(self) -> None:
        with self._connection as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS db_version
                (
                    table_name  TEXT    NOT NULL PRIMARY KEY,
                    version     INTEGER NOT NULL DEFAULT 1
                );
                """
            )

            cursor = connection.execute("SELECT table_name, version FROM db_version;")
            table_version: dict[str, int] = {}

            for table_name, version in cursor:
                table_version[table_name] = version

            if table_version.get("module_chapter", 1) == 1:
                connection.execute(
                    """
                    CREATE TABLE module_chapter_temp(
                        rowid           INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        manga_rowid     INTEGER NOT NULL,
                        language        TEXT NOT NULL DEFAULT "en",
                        scanlator_group TEXT NOT NULL,
                        chapter_number  REAL NOT NULL,
                        volume_number   REAL DEFAULT NULL,
                        chapter_title   TEXT NOT NULL,
                        link            TEXT NOT NULL,
                        uploaded        INTEGER NOT NULL DEFAULT 0,
                        skip_upload     INTEGER NOT NULL DEFAULT 0,
                        UNIQUE (manga_rowid, language ASC, scanlator_group ASC, chapter_number ASC)
                    );
                    """
                )

                connection.execute(
                    """
                    INSERT INTO module_chapter_temp(
                        manga_rowid,
                        language,
                        scanlator_group,
                        chapter_number,
                        chapter_title,
                        link,
                        uploaded,
                        skip_upload
                    )
                    SELECT ref_id, language, scanlator_group, number, chapter_title, link, uploaded, skip_upload
                    FROM module_chapter;
                    """
                )

                connection.execute("DROP TABLE module_chapter;")
                connection.execute("ALTER TABLE module_chapter_temp RENAME TO module_chapter;")
                connection.execute("INSERT INTO db_version(table_name, version) VALUES (?, ?);", ("module_chapter", 2))

            if table_version.get("module_manga", 1) == 1:
                connection.execute(
                    """
                    CREATE TABLE module_manga_temp(
                        rowid           INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        module_id       TEXT    NOT NULL,
                        link            TEXT    NOT NULL,
                        title           TEXT    DEFAULT NULL,
                        alt_titles      TEXT    DEFAULT NULL,
                        mangabaka_id    INTEGER DEFAULT NULL,
                        mangadotnet_id  INTEGER DEFAULT NULL,
                        last_checked    INTEGER DEFAULT NULL,
                        manual_override INTEGER NOT NULL DEFAULT 0,
                        UNIQUE (module_id, link),
                        FOREIGN KEY (rowid) REFERENCES module_chapter(manga_rowid) ON UPDATE CASCADE ON DELETE CASCADE
                    );
                    """
                )

                connection.execute(
                    """
                    INSERT INTO module_manga_temp(
                        rowid,
                        module_id,
                        link,
                        title,
                        alt_titles,
                        mangabaka_id,
                        mangadotnet_id,
                        last_checked,
                        manual_override
                    )
                    SELECT rowid, module_id, link, title, alt_titles, mangabaka_id, mangadotnet_id, last_checked, manual_override
                    FROM module_manga;
                    """
                )

                connection.execute("DROP TABLE module_manga;")
                connection.execute("ALTER TABLE module_manga_temp RENAME TO module_manga;")
                connection.execute("INSERT INTO db_version(table_name, version) VALUES (?, ?);", ("module_manga", 2))

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()

    def _execute(self, sql: Template) -> Cursor:
        query = ""

        for t_string in sql:
            if isinstance(t_string, Interpolation):
                query += "?"
            else:
                query += t_string

        return self._connection.execute(query, sql.values)

    def add_module_listing(self, module_id: str, title: str, link: str) -> None:
        with self._connection:
            self._execute(
                t"INSERT OR IGNORE INTO module_manga(module_id, link, title) VALUES ({module_id}, {link}, {title});"
            )

    def get_module_listing(self, module_id: str, only_old_entries: bool = True) -> tuple[int, Cursor]:
        if only_old_entries:
            count = self._execute(
                t"""
                SELECT COUNT(*)
                FROM module_manga
                WHERE module_id = {module_id} AND (last_checked IS NULL OR last_checked <= unixepoch('now', '-12 hours'));
                """
            )

            cursor = self._execute(
                t"""
                SELECT rowid, link, title, mangabaka_id, mangadotnet_id, manual_override
                FROM module_manga
                WHERE module_id = {module_id} AND (last_checked IS NULL OR last_checked <= unixepoch('now', '-12 hours'))
                ORDER BY title ASC;
                """
            )
        else:
            count = self._execute(t"SELECT COUNT(*) FROM module_manga WHERE module_id = {module_id};")

            cursor = self._execute(
                t"""
                SELECT rowid, link, title, mangabaka_id, mangadotnet_id, manual_override
                FROM module_manga
                WHERE module_id = {module_id}
                ORDER BY title ASC;
                """
            )

        return count.fetchone()[0], cursor

    def add_module_manga(self, rowid: int, manga: ModuleManga) -> None:
        with self._connection:
            self._execute(
                t"""
                UPDATE module_manga
                SET title = {manga.title}, 
                    alt_titles = {"\n".join(manga.alt_titles)},
                    mangabaka_id = {manga.mangabaka_id},
                    mangadotnet_id = {manga.mangadotnet_id},
                    last_checked = unixepoch('now')
                WHERE rowid = {rowid};
                """
            )

            for chapter in manga.chapters:
                self._execute(
                    t"""
                    INSERT OR IGNORE INTO module_chapter(
                        manga_rowid, language, scanlator_group, chapter_number, volume_number, chapter_title, link, uploaded
                    ) VALUES (
                        {rowid},
                        {chapter.language},
                        {chapter.scanlator_group},
                        {chapter.chapter_number},
                        {chapter.volume_number},
                        {chapter.chapter_title},
                        {chapter.link},
                        {chapter.uploaded}
                    );
                    """
                )

                self._execute(
                    t"""
                    UPDATE module_chapter
                    SET 
                        volume_number = {chapter.volume_number},
                        chapter_title = {chapter.chapter_title},
                        link = {chapter.link},
                        uploaded = {chapter.uploaded}
                    WHERE
                        manga_rowid = {rowid} AND
                        language = {chapter.language} AND
                        scanlator_group = {chapter.scanlator_group} AND
                        chapter_number = {chapter.chapter_number};
                    """
                )

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
            SELECT rowid, link, title, mangadotnet_id
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
            SELECT manga_rowid, language, scanlator_group, chapter_number, volume_number, chapter_title, link
            FROM module_chapter
            WHERE manga_rowid = {manga_rowid} AND uploaded = 0 AND skip_upload = 0
            ORDER BY language, scanlator_group, chapter_number;
            """
        )

    def mark_chapter_uploaded(self, manga_rowid: int, language: str, scanlator_group: str, chapter_number: float) -> None:
        with self._connection:
            self._execute(
                t"""
                UPDATE module_chapter SET uploaded = 1
                WHERE
                    manga_rowid = {manga_rowid} AND
                    language = {language} AND
                    scanlator_group = {scanlator_group} AND
                    chapter_number = {chapter_number};
                """
            )
