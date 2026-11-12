from mangadotnet_scraper.config import Config
from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates.iken import IkenTemplate


class KenScansSourceProvider(IkenTemplate):
    def __init__(self, config: Config) -> None:
        super().__init__(
            config,
            group_name="Kenscans",
            source_id="en.ken_scans",
            name="Ken Scans",
            version=1,
            languages=["en"],
            base_url="https://kencomics.com",
            base_api_url="https://api.kencomics.com",
        )


SourceProvider.register_source(KenScansSourceProvider)
