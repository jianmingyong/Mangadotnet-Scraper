from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.template.keyoapp import KeyoAppTemplate


class ArtLapsaModule(KeyoAppTemplate):
    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        super().__init__(
            config,
            module_id="art_lapsa",
            display_name="Art Lapsa",
            language="en",
            version=1,
            base_url="https://artlapsa.com",
            group_name="Art Lapsa",
            base_cdn_url="https://cdn.artlapsa.com",
        )
