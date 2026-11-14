import json
from collections.abc import Collection, Sequence
from string.templatelib import Interpolation, Template, convert
from typing import Final, Literal, cast, override

from cysqlite import Connection, Cursor, Row
from cysqlite import connect as cysqlite_connect

from mangadotnet_scraper.data.base import (
    DataProvider,
    SourceEntryChapterEntity,
    SourceEntryEntity,
)


class SqliteDataProvider(DataProvider):
    _connection: Final[Connection]

    def __init__(self, database: str = "data.db") -> None:
        self._connection = cysqlite_connect(
            database if database is not None else "data.db",
            row_factory=Row,
            pragmas={"foreign_keys": 1},
        )
        self.initialize()

    @override
    def initialize(self) -> None:
        with self._connection.atomic():
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS db_version
                (
                    table_name  TEXT    NOT NULL PRIMARY KEY,
                    version     INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS source
                (
                    source_id   TEXT    NOT NULL    PRIMARY KEY,
                    version     INTEGER NOT NULL    DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS source_entry
                (
                    rowid                   INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    source_id               TEXT    NOT NULL,
                    manga_id                TEXT    NOT NULL,
                    link                    TEXT    NOT NULL,
                    title                   TEXT    NOT NULL,
                    alt_titles              TEXT    DEFAULT NULL,
                    mangabaka_id            INTEGER DEFAULT NULL,
                    mangadotnet_id          INTEGER DEFAULT NULL,
                    manual_mapping_override INTEGER NOT NULL DEFAULT 0,
                    skip_upload             INTEGER NOT NULL DEFAULT 0,
                    chapters                TEXT    DEFAULT NULL,
                    CONSTRAINT source_entry_unique_manga_id UNIQUE (source_id, manga_id)
                    CONSTRAINT source_entry_unique_link UNIQUE (source_id, link)
                );

                INSERT OR IGNORE INTO db_version (table_name, version) VALUES 
                    ('source', 1),
                    ('source_entry', 1);
                """
            )

            cursor = self._connection.execute(
                "SELECT table_name, version FROM db_version;"
            )

            table_version: dict[str, int] = {}

            for table_name, version in cursor:
                table_version[table_name] = version

            if "module_manga" in table_version:
                self._connection.executescript(
                    """
                    INSERT INTO source_entry (
                        rowid,
                        source_id,
                        manga_id,
                        link,
                        title,
                        alt_titles,
                        mangabaka_id,
                        mangadotnet_id,
                        manual_mapping_override,
                        skip_upload
                    ) SELECT
                        rowid,
                        module_id,
                        manga_id,
                        link,
                        title,
                        alt_titles,
                        mangabaka_id,
                        mangadotnet_id,
                        manual_override,
                        skip_upload 
                    FROM module_manga;

                    DROP TABLE IF EXISTS module;
                    DROP TABLE IF EXISTS module_chapter;
                    DROP TABLE IF EXISTS module_manga;

                    DELETE FROM db_version WHERE table_name = 'module' OR table_name = 'module_manga' OR table_name = 'module_chapter';
                    """
                )

    @override
    def close(self) -> None:
        if self._connection is None:
            return

        if self._connection.in_transaction:
            self._connection.commit()

        self._connection.close(True)

    @override
    def add_source_entry(
        self, source_id: str, manga_id: str, title: str, link: str
    ) -> bool:
        with self._connection.atomic():
            count: int = self._execute(
                t"""
                SELECT COUNT(*)
                FROM source_entry
                WHERE source_id = {source_id} AND (manga_id = {manga_id} OR link = {link});
                """
            ).scalar()

            if count == 0:
                # No duplicate exists, safe to add into the db
                self._execute(
                    t"""
                    INSERT INTO source_entry (
                        source_id,
                        manga_id,
                        link,
                        title
                    ) VALUES ({source_id}, {manga_id}, {link}, {title});
                    """
                )
                return True
            else:
                return False

    @override
    def delete_source_entry(self, id: int) -> None:
        with self._connection.atomic():
            self._execute(t"DELETE FROM source_entry WHERE rowid = {id};")

    @override
    def get_source_entries(
        self,
        source_id: str,
        offset: int = 0,
        limit: int = -1,
        order_by: Literal["rowid", "title"] | None = None,
        order: Literal["ASC", "DESC"] = "ASC",
    ) -> Sequence[SourceEntryEntity]:
        cursor = self._execute(
            t"""
            SELECT 
                rowid,
                source_id,
                manga_id,
                title,
                alt_titles,
                link,
                mangabaka_id,
                mangadotnet_id,
                manual_mapping_override,
                skip_upload,
                chapters
            FROM source_entry
            WHERE
                source_id = {source_id} AND
                rowid > {offset}
            ORDER BY {order_by} {order:l}
            ;
            """
        )

        rows = cursor.fetchall() if limit == -1 else cursor.fetchmany(limit)
        result = []

        for row in rows:
            if row["alt_titles"] is None:
                alt_titles = []
            else:
                alt_titles = cast(str, row["alt_titles"]).splitlines()

            chapters = []

            if row["chapters"] is not None:
                chapters_data = json.loads(row["chapters"])

                for chapter in chapters_data:
                    chapters.append(
                        SourceEntryChapterEntity(
                            chapter_id=chapter["chapter_id"],
                            language=chapter["language"],
                            group=chapter["group"],
                            type=chapter["type"],
                            chapter_number=chapter["chapter_number"],
                            volume_number=chapter["volume_number"],
                            title=chapter["title"],
                            link=chapter["link"],
                            is_uploaded=chapter["is_uploaded"],
                        )
                    )

            result.append(
                SourceEntryEntity(
                    rowid=row["rowid"],
                    source_id=row["source_id"],
                    manga_id=row["manga_id"],
                    title=row["title"],
                    alt_titles=alt_titles,
                    link=row["link"],
                    mangabaka_id=row["mangabaka_id"],
                    mangadotnet_id=row["mangadotnet_id"],
                    manual_mapping_override=row["manual_mapping_override"] > 0,
                    skip_upload=row["skip_upload"] > 0,
                    chapters=chapters,
                )
            )

        return result

    def _execute(self, sql: Template) -> Cursor:
        query = ""
        values = []

        for t_string in sql:
            if isinstance(t_string, Interpolation):
                value = convert(t_string.value, t_string.conversion)

                if isinstance(value, str) and t_string.format_spec == "l":
                    query += value
                elif not isinstance(value, str) and isinstance(
                    value, Collection
                ):
                    query += ",".join("?" for _ in range(len(value)))
                    values.extend(value)
                else:
                    query += "?"
                    values.append(
                        format(value, t_string.format_spec)
                        if t_string.format_spec != ""
                        else value
                    )
            else:
                query += t_string

        return self._connection.execute(query, values)
