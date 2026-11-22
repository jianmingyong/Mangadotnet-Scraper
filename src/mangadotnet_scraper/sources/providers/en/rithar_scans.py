from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates import KeyoAppLivewireTemplate


class RitharScansSourceProvider(KeyoAppLivewireTemplate):
    def __init__(self, **kwargs) -> None:
        super().__init__(
            group_name="Rithar Scans",
            base_cdn_url="https://cdn.ritharscans.com",
            source_id="en.rithar_scans",
            name="Rithar Scans",
            version=1,
            languages=["en"],
            base_url="https://ritharscans.com",
            **kwargs,
        )


SourceProvider.register_source(RitharScansSourceProvider)
