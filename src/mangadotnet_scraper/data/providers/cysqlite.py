from collections.abc import Iterator
from typing import Final, Literal, override

from peewee import IntegrityError
from playhouse.cysqlite_ext import CySqliteDatabase
from playhouse.migrate import SchemaMigrator, SqliteMigrator, migrate

from mangadotnet_scraper.data import Data
from mangadotnet_scraper.data.entities import Source, SourceEntry, TableVersion


class CySqliteData(Data):
    database: Final[CySqliteDatabase]

    def __init__(self, database: str = "data.db") -> None:
        self.database = CySqliteDatabase(
            database,
            pragmas={
                "journal_mode": "wal",
                "foreign_keys": 1,
            },
        )

    @override
    def initialize(self) -> None:
        self.database.connect()
        self.database.bind([TableVersion, Source, SourceEntry])

        with self.database.atomic():
            self.database.create_tables([TableVersion, Source, SourceEntry])

            TableVersion.insert_many(
                [
                    {"table_name": "source", "version": 1},
                    {"table_name": "source_entry", "version": 1},
                ]
            ).on_conflict_ignore().execute()

        migrator: SqliteMigrator = SchemaMigrator.from_database(self.database)

        module_manga = TableVersion.get_or_none(
            TableVersion.table_name == "module_manga"
        )

        if module_manga is not None:
            with self.database.atomic():
                migrate(
                    migrator.sql(
                        """
                        INSERT INTO source_entry (
                            rowid,
                            source_id,
                            manga_id,
                            link,
                            title,
                            alt_titles,
                            mangabaka_id,
                            mangadot_id,
                            manual_mapping_override,
                            skip_upload,
                            chapters
                        ) SELECT
                            rowid,
                            CONCAT('en.', module_id),
                            manga_id,
                            link,
                            title,
                            alt_titles,
                            mangabaka_id,
                            mangadotnet_id,
                            manual_override,
                            skip_upload,
                            '[]'
                        FROM module_manga;
                        """
                    ),
                    migrator.drop_table("module"),
                    migrator.drop_table("module_chapter"),
                    migrator.drop_table("module_manga"),
                )

                TableVersion.delete().where(
                    # pyrefly: ignore[bad-argument-count]
                    TableVersion.table_name.in_(
                        # pyrefly: ignore[bad-argument-type]
                        ["module", "module_manga", "module_chapter"]
                    )
                ).execute()

    @override
    def close(self) -> None:
        if not self.database.is_closed:
            self.database.close()

    @override
    def add_source_entry(
        self, source_id: str, manga_id: str, title: str, link: str
    ) -> bool:
        try:
            with self.database.atomic():
                SourceEntry.create(
                    source_id=source_id,
                    manga_id=manga_id,
                    title=title,
                    link=link,
                )
            return True
        except IntegrityError:
            return False

    @override
    def delete_source_entry(self, id: int) -> None:
        with self.database.atomic():
            SourceEntry.delete_by_id(id)

    @override
    def get_source_entry(self, rowid: int) -> SourceEntry:
        return SourceEntry.get_by_id(rowid)

    @override
    def get_source_entries(
        self,
        source_id: str,
        order_by: Literal["rowid", "title"] = "rowid",
    ) -> Iterator[SourceEntry]:
        match order_by:
            case "rowid":
                _order_by = SourceEntry.rowid

            case "title":
                _order_by = SourceEntry.title

        return (
            SourceEntry.select()
            .where(SourceEntry.source_id == source_id)
            .order_by(_order_by)
            .iterator()
        )

    @override
    def update_source_entry(self, entry: SourceEntry) -> None:
        with self.database.atomic():
            entry.save(only=entry.dirty_fields)
