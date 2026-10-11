from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.templates.ezmanhwa import EzManhwaTemplate


class QiScansModule(EzManhwaTemplate):
    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        super().__init__(
            config,
            group_name="Qi Manhwa",
            module_id="qi_scans",
            display_name="Qi Scans",
            language="en",
            version=1,
            base_url="https://qimanga.com",
            base_api_url="https://api.qimanga.com",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0",
        )
