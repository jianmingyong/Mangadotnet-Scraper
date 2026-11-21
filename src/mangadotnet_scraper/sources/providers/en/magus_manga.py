from mangadotnet_scraper.camoufox_utils import Browser
from mangadotnet_scraper.config import Config
from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates.iken import IkenTemplate


class MagusMangaSourceProvider(IkenTemplate):
    def __init__(self, config: Config, browser: Browser) -> None:
        super().__init__(
            config,
            browser,
            group_name="MagusManga",
            source_id="en.magus_manga",
            name="Magus Manga",
            version=1,
            languages=["en"],
            base_url="https://magustoon.org",
            base_api_url="https://api.magustoon.org",
        )


SourceProvider.register_source(MagusMangaSourceProvider)
