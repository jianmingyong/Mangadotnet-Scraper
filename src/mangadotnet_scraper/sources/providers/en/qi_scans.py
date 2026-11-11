from mangadotnet_scraper.config import Config
from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates.ezmanhwa import EzManhwaTemplate


class QiScansSourceProvider(EzManhwaTemplate):
    def __init__(self, config: Config) -> None:
        super().__init__(
            config,
            group_name="Qi Manhwa",
            base_api_url="https://api.qimanga.com",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:159.0) Gecko/20100101 Firefox/159.0",
            source_id="en.qi_scans",
            name="Qi Scans",
            version=1,
            languages=["en"],
            base_url="https://qimanga.com",
        )


SourceProvider.register_source(QiScansSourceProvider)
