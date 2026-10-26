from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.manager import ModuleManager
from mangadotnet_scraper.modules.templates.keyoapp import (
    KeyoAppLivewireTemplate,
)


class ArtLapsaModule(KeyoAppLivewireTemplate):
    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        super().__init__(
            config,
            group_name="Art Lapsa",
            module_id="art_lapsa",
            display_name="Art Lapsa",
            language="en",
            version=1,
            base_url="https://artlapsa.com",
            base_cdn_url="https://cdn.artlapsa.com",
        )


ModuleManager.register_module(ArtLapsaModule)
