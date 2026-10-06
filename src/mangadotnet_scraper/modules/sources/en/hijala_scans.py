from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.templates.iken import IkenTemplate


class HijalaScansModule(IkenTemplate):
    def __init__(self, config: MangaDotNetScraperConfig):
        super().__init__(
            config,
            module_id="hijala_scans",
            display_name="Hijala Scans",
            language="en",
            version=1,
            base_url="https://en-hijala.com",
            base_api_url="https://api.en-hijala.com",
            group_name="Hijala Translations",
        )
