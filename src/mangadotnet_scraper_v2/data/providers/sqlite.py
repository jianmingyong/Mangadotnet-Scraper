from typing import Final

from cysqlite import Connection
from cysqlite import connect as cysqlite_connect

from mangadotnet_scraper_v2.data.base import DataProvider


class SqliteDataProvider(DataProvider):
    _connection: Final[Connection]

    def __init__(self, database: str) -> None:
        self._connection = cysqlite_connect(
            database, pragmas={"foreign_keys": 1}
        )
        self.initialize()

    def initialize(self) -> None:
        with self._connection.atomic():
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS db_version
                (
                    table_name  TEXT    NOT NULL PRIMARY KEY,
                    version     INTEGER NOT NULL DEFAULT 1
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
                );

                INSERT OR IGNORE INTO db_version (table_name, version) VALUES ("source_entry", 1);
                """
            )

    def close(self) -> None:
        if self._connection is None:
            return

        if self._connection.in_transaction:
            self._connection.commit()

        self._connection.close(True)
