from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates.iken import IkenTemplate


class SanaScansSourceProvider(IkenTemplate):
    def __init__(self, **kwargs) -> None:
        super().__init__(
            group_name="Sana Scans",
            source_id="en.sana_scans",
            name="Sana Scans",
            version=1,
            languages=["en"],
            base_url="https://sanascans.com",
            base_api_url="https://api.sanascans.com",
            **kwargs,
        )


SourceProvider.register_source(SanaScansSourceProvider)
