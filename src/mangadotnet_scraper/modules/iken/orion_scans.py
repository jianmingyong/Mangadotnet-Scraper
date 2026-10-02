from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.iken.base import IkenTemplate


class OrionScansModule(IkenTemplate):
    def __init__(self, config: MangaDotNetScraperConfig):
        super().__init__(
            config,
            module_id="orion_scans",
            display_name="Orion Scans",
            base_url="https://orion-scans.com",
            base_api_url="https://api.orion-scans.com",
        )
