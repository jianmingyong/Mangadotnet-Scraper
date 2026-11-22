from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates.iken import IkenTemplate


class OrionScansSourceProvider(IkenTemplate):
    def __init__(
        self,
        **kwargs,
    ) -> None:
        super().__init__(
            group_name="Orion Scans",
            source_id="en.orion_scans",
            name="Orion Scans",
            version=1,
            languages=["en"],
            base_url="https://orion-scans.com",
            base_api_url="https://api.orion-scans.com",
            **kwargs,
        )


SourceProvider.register_source(OrionScansSourceProvider)
