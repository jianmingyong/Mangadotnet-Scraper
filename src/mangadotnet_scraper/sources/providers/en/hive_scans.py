from mangadotnet_scraper.config import Config
from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates.iken import IkenTemplate


class HiveScansSourceProvider(IkenTemplate):
    def __init__(self, config: Config) -> None:
        super().__init__(
            config,
            group_name="HiveToons",
            base_api_url="https://api.hivetoons.org",
            source_id="en.hive_scans",
            name="Hive Toons",
            version=1,
            languages=["en"],
            base_url="https://hivetoons.org",
        )


SourceProvider.register_source(HiveScansSourceProvider)
