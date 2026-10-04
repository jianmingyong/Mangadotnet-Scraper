from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.template.iken import IkenTemplate


class HiveScansModule(IkenTemplate):
    def __init__(self, config: MangaDotNetScraperConfig):
        super().__init__(
            config,
            module_id="hive_scans",
            display_name="Hive Scans",
            language="en",
            version=1,
            base_url="https://hivetoons.org",
            base_api_url="https://api.hivetoons.org",
            group_name="Hive Scans",
        )
