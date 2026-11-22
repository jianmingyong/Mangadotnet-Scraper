from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates import KeyoAppLivewireTemplate


class ArtLapsaSourceProvider(KeyoAppLivewireTemplate):
    def __init__(self, **kwargs) -> None:
        super().__init__(
            group_name="Art Lapsa",
            base_cdn_url="https://cdn.artlapsa.com",
            source_id="en.art_lapsa",
            name="Art Lapsa",
            version=1,
            languages=["en"],
            base_url="https://artlapsa.com",
            **kwargs,
        )


SourceProvider.register_source(ArtLapsaSourceProvider)
