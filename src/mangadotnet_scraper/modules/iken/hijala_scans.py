from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.iken.base import IkenTemplate


class HijalaScansModule(IkenTemplate):
    def __init__(self, config: MangaDotNetScraperConfig):
        super().__init__(
            config,
            module_id="hijala_scans",
            display_name="Hijala Translations",
            base_url="https://en-hijala.com",
            base_api_url="https://api.en-hijala.com",
        )
