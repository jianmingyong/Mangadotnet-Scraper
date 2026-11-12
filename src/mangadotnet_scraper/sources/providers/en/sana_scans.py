from mangadotnet_scraper.config import Config
from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates.iken import IkenTemplate


class SanaScansSourceProvider(IkenTemplate):
    def __init__(self, config: Config) -> None:
        super().__init__(
            config,
            group_name="Sana Scans",
            source_id="en.sana_scans",
            name="Sana Scans",
            version=1,
            languages=["en"],
            base_url="https://sanascans.com",
            base_api_url="https://api.sanascans.com",
        )


SourceProvider.register_source(SanaScansSourceProvider)
