from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.iken.base import IkenTemplate


class SanaScansModule(IkenTemplate):
    def __init__(self, config: MangaDotNetScraperConfig):
        super().__init__(
            config,
            module_id="sana_scans",
            display_name="Sana Scans",
            base_url="https://sanascans.com",
            base_api_url="https://api.sanascans.com",
        )
