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
    group: str
    number: int | float
    title: str
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
                CREATE TABLE IF NOT EXISTS module_manga
                (
                    module_id       TEXT NOT NULL,
                    link            TEXT NOT NULL,
                    title           TEXT    DEFAULT NULL,
                    alt_titles      TEXT    DEFAULT NULL,
                    mangabaka_id    INTEGER DEFAULT NULL,
                    mangadotnet_id  INTEGER DEFAULT NULL,
                    last_checked    INTEGER DEFAULT NULL,
                    manual_override INTEGER DEFAULT 0 NOT NULL,
                    UNIQUE (module_id, link)
                );
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS module_chapter
                (
                    ref_id          INTEGER NOT NULL,
                    language        TEXT DEFAULT "en" NOT NULL,
                    scanlator_group TEXT NOT NULL,
                    number          REAL NOT NULL,
                    chapter_title   TEXT NOT NULL,
                    link            TEXT NOT NULL,
                    uploaded        INTEGER DEFAULT 0 NOT NULL,
                    skip_upload     INTEGER DEFAULT 0 NOT NULL,
                    FOREIGN KEY (ref_id) REFERENCES module_manga (rowid) ON DELETE CASCADE,
                    UNIQUE (ref_id, language, scanlator_group, number ASC)
                );
                """
            )

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

    def get_module_listing(
        self, module_id: str, only_old_entries: bool = True, only_unmapped_entries: bool = True
    ) -> tuple[int, Cursor]:
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
                    INSERT OR IGNORE INTO module_chapter(ref_id, language, scanlator_group, number, chapter_title, link, uploaded) VALUES
                    ({rowid}, {chapter.language}, {chapter.group}, {chapter.number}, {chapter.title}, {chapter.link}, {chapter.uploaded});
                    """
                )

                self._execute(
                    t"""
                    UPDATE module_chapter
                    SET chapter_title = {chapter.title}, link = {chapter.link}, uploaded = {chapter.uploaded}
                    WHERE ref_id = {rowid} AND language = {chapter.language} AND scanlator_group = {chapter.group} AND number = {chapter.number};
                    """
                )

    def get_non_uploaded_manga(self, module_id: str) -> tuple[int, Cursor]:
        count = self._execute(
            t"""
            SELECT COUNT(*)
            FROM module_manga
            WHERE
                module_id = {module_id} AND
                rowid IN (SELECT DISTINCT ref_id FROM module_chapter WHERE uploaded = 0) AND
                mangadotnet_id IS NOT NULL;
            """
        )

        return count.fetchone()[0], self._execute(
            t"""
            SELECT rowid, link, title, mangadotnet_id
            FROM module_manga
            WHERE
                module_id = {module_id} AND
                rowid IN (SELECT DISTINCT ref_id FROM module_chapter WHERE uploaded = 0) AND
                mangadotnet_id IS NOT NULL
            ORDER BY module_id, title;
            """
        )

    def get_chapters(self, ref_id: int, uploaded: bool | None = None) -> tuple[int, Cursor]:
        if uploaded is None:
            count = self._execute(
                t"""
                SELECT COUNT(*)
                FROM module_chapter
                WHERE ref_id = {ref_id};
                """
            )

            return count.fetchone()[0], self._execute(
                t"""
                SELECT ref_id, language, scanlator_group, number, chapter_title, link
                FROM module_chapter
                WHERE ref_id = {ref_id}
                ORDER BY language, scanlator_group, number;
                """
            )
        else:
            count = self._execute(
                t"""
                SELECT COUNT(*)
                FROM module_chapter
                WHERE ref_id = {ref_id} AND uploaded = {uploaded};
                """
            )

            return count.fetchone()[0], self._execute(
                t"""
                SELECT ref_id, language, scanlator_group, number, chapter_title, link
                FROM module_chapter
                WHERE ref_id = {ref_id} AND uploaded = {uploaded}
                ORDER BY language, scanlator_group, number;
                """
            )

    def mark_chapter_uploaded(self, ref_id: int, language: str, scanlator_group: str, number: float):
        with self._connection:
            self._execute(
                t"""
                UPDATE module_chapter SET uploaded = 1
                WHERE ref_id = {ref_id} AND language = {language} AND scanlator_group = {scanlator_group} AND number = {number};
                """
            )
