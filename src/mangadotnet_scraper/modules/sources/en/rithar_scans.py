from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.templates.keyoapp import (
    KeyoAppLivewireTemplate,
)


class RitharScansModule(KeyoAppLivewireTemplate):
    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        super().__init__(
            config,
            group_name="Rithar Scans",
            module_id="rithar_scans",
            display_name="Rithar Scans",
            language="en",
            version=1,
            base_url="https://ritharscans.com",
            base_cdn_url="https://cdn.ritharscans.com",
        )
