from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates.iken import IkenTemplate


class HiveScansSourceProvider(IkenTemplate):
    def __init__(self, **kwargs) -> None:
        super().__init__(
            group_name="HiveToons",
            source_id="en.hive_scans",
            name="Hive Toons",
            version=1,
            languages=["en"],
            base_url="https://hivetoons.org",
            base_api_url="https://api.hivetoons.org",
            **kwargs,
        )


SourceProvider.register_source(HiveScansSourceProvider)
