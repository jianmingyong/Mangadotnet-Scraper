from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.iken.base import IkenTemplate


class VortexScansModule(IkenTemplate):
    def __init__(self, config: MangaDotNetScraperConfig):
        super().__init__(
            config,
            module_id="vortex_scans",
            display_name="Vortex Scans",
            base_url="https://vortexscans.org",
            base_api_url="https://api.vortexscans.org",
        )
