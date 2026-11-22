from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates import IkenTemplate


class HijalaScansSourceProvider(IkenTemplate):
    def __init__(
        self,
        **kwargs,
    ) -> None:
        super().__init__(
            group_name="Hijala Translations",
            source_id="en.hijala_scans",
            name="Hijala Scans",
            version=1,
            languages=["en"],
            base_url="https://en-hijala.com",
            base_api_url="https://api.en-hijala.com",
            **kwargs,
        )


SourceProvider.register_source(HijalaScansSourceProvider)
