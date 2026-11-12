from mangadotnet_scraper.config import Config
from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates.iken import IkenTemplate


class VortexScansSourceProvider(IkenTemplate):
    def __init__(self, config: Config) -> None:
        super().__init__(
            config,
            group_name="Vortex Scans",
            source_id="en.vortex_scans",
            name="Vortex Scans",
            version=1,
            languages=["en"],
            base_url="https://vortexscans.org",
            base_api_url="https://api.vortexscans.org",
        )


SourceProvider.register_source(VortexScansSourceProvider)
