from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.iken.base import IkenTemplate


class OrionScansModule(IkenTemplate):
    def __init__(self, config: MangaDotNetScraperConfig):
        super().__init__(
            config,
            module_id="ken_scans",
            display_name="Kenscans",
            base_url="https://kencomics.com",
            base_api_url="https://api.kencomics.com",
        )
