from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.template.iken import IkenTemplate


class OrionScansModule(IkenTemplate):
    def __init__(self, config: MangaDotNetScraperConfig):
        super().__init__(
            config,
            module_id="orion_scans",
            display_name="Orion Scans",
            language="en",
            version=1,
            base_url="https://orion-scans.com",
            base_api_url="https://api.orion-scans.com",
            group_name="Orion Scans",
        )
