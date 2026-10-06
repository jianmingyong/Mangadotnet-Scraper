from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.templates.iken import IkenTemplate


class MagusMangaModule(IkenTemplate):
    def __init__(self, config: MangaDotNetScraperConfig):
        super().__init__(
            config,
            module_id="magus_manga",
            display_name="Magus Manga",
            language="en",
            version=1,
            base_url="https://magustoon.org",
            base_api_url="https://api.magustoon.org",
            group_name="MagusManga",
        )
