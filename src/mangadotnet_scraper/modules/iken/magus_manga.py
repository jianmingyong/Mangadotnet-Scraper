from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.iken.base import IkenTemplate


class MagusMangaModule(IkenTemplate):
    def __init__(self, config: MangaDotNetScraperConfig):
        super().__init__(
            config,
            module_id="magus_manga",
            display_name="MagusManga",
            base_url="https://magustoon.org",
            base_api_url="https://api.magustoon.org",
        )
