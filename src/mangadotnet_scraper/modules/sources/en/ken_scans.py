from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.templates.iken import IkenTemplate


class KenScansModule(IkenTemplate):
    def __init__(self, config: MangaDotNetScraperConfig):
        super().__init__(
            config,
            module_id="ken_scans",
            display_name="Ken Scans",
            language="en",
            version=1,
            base_url="https://kencomics.com",
            base_api_url="https://api.kencomics.com",
            group_name="Kenscans",
        )
