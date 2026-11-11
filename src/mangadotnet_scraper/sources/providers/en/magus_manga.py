from mangadotnet_scraper.config import Config
from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates.iken import IkenTemplate


class MagusMangaSourceProvider(IkenTemplate):
    def __init__(self, config: Config) -> None:
        super().__init__(
            config,
            group_name="MagusManga",
            base_api_url="https://api.magustoon.org",
            source_id="en.magus_manga",
            name="Magus Manga",
            version=1,
            languages=["en"],
            base_url="https://magustoon.org",
        )


SourceProvider.register_source(MagusMangaSourceProvider)
