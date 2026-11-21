from mangadotnet_scraper.camoufox_utils import Browser
from mangadotnet_scraper.config import Config
from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates import KeyoAppLivewireTemplate


class KitsuneDawnSourceProvider(KeyoAppLivewireTemplate):
    def __init__(self, config: Config, browser: Browser) -> None:
        super().__init__(
            config,
            browser,
            group_name="kitsunedawn",
            base_cdn_url="https://cdn.kitsunedawn.com",
            source_id="en.kitsune_dawn",
            name="Kitsune Dawn",
            version=1,
            languages=["en"],
            base_url="https://kitsunedawn.com",
        )


SourceProvider.register_source(KitsuneDawnSourceProvider)
