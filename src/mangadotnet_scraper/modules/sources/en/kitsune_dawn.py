from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.templates.keyoapp import KeyoAppTemplate


class KitsuneDawnModule(KeyoAppTemplate):
    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        super().__init__(
            config,
            group_name="kitsunedawn",
            module_id="kitsune_dawn",
            display_name="Kitsune Dawn",
            language="en",
            version=1,
            base_url="https://kitsunedawn.com",
            base_cdn_url="https://cdn.kitsunedawn.com",
        )
