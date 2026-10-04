from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.template.iken import IkenTemplate


class RenaScansModule(IkenTemplate):
    def __init__(self, config: MangaDotNetScraperConfig):
        super().__init__(
            config,
            module_id="rena_scans",
            display_name="Rena Scans",
            language="en",
            version=1,
            base_url="https://renascans.net",
            base_api_url="https://api.renascans.net",
            group_name="Renascans",
        )
