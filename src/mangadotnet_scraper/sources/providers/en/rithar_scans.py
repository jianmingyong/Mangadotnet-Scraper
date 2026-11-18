from mangadotnet_scraper.config import ConfigProvider
from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates import KeyoAppLivewireTemplate


class RitharScansSourceProvider(KeyoAppLivewireTemplate):
    def __init__(self, config: ConfigProvider) -> None:
        super().__init__(
            config,
            group_name="Rithar Scans",
            base_cdn_url="https://cdn.ritharscans.com",
            source_id="en.rithar_scans",
            name="Rithar Scans",
            version=1,
            languages=["en"],
            base_url="https://ritharscans.com",
        )


SourceProvider.register_source(RitharScansSourceProvider)
