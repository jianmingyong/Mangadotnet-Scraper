from mangadotnet_scraper.config import Config
from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates.ezmanhwa import EzManhwaTemplate


class QiScansSourceProvider(EzManhwaTemplate):
    def __init__(self, config: Config) -> None:
        super().__init__(
            config,
            group_name="Qi Manhwa",
            source_id="en.qi_scans",
            name="Qi Scans",
            version=1,
            languages=["en"],
            base_url="https://qimanga.com",
            base_api_url="https://api.qimanga.com",
        )


SourceProvider.register_source(QiScansSourceProvider)
