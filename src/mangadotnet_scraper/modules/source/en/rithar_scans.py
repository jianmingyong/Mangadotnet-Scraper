from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.template.keyoapp import KeyoAppTemplate


class RitharScansModule(KeyoAppTemplate):
    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        super().__init__(
            config,
            module_id="rithar_scans",
            display_name="Rithar Scans",
            language="en",
            version=1,
            base_url="https://ritharscans.com",
            group_name="Rithar Scans",
            base_cdn_url="https://cdn.ritharscans.com",
        )
