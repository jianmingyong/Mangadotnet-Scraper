from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates.iken import IkenTemplate


class KenScansSourceProvider(IkenTemplate):
    def __init__(self, **kwargs) -> None:
        super().__init__(
            group_name="Kenscans",
            source_id="en.ken_scans",
            name="Ken Scans",
            version=1,
            languages=["en"],
            base_url="https://kencomics.com",
            base_api_url="https://api.kencomics.com",
            **kwargs,
        )


SourceProvider.register_source(KenScansSourceProvider)
