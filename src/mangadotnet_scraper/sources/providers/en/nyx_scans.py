from mangadotnet_scraper.config import Config
from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates.iken import IkenTemplate


class NyxScansSourceProvider(IkenTemplate):
    def __init__(self, config: Config) -> None:
        super().__init__(
            config,
            group_name="Nyx Scans",
            base_api_url="https://api.nyxscans.com",
            source_id="en.nyx_scans",
            name="Nyx Scans",
            version=1,
            languages=["en"],
            base_url="https://nyxscans.com",
        )


SourceProvider.register_source(NyxScansSourceProvider)
