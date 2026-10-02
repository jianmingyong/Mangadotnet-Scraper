from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.keyoapp.base import KeyoAppTemplate


class ArtLapsaModule(KeyoAppTemplate):
    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        super().__init__(
            config,
            module_id="art_lapsa",
            display_name="Art Lapsa",
            base_url="https://artlapsa.com",
            base_cdn_url="https://cdn.artlapsa.com",
        )
