from typing import override

from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.iken.base import IkenTemplate


class NyxScansModule(IkenTemplate):
    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        super().__init__(
            config,
            module_id="nyx_scans",
            display_name="Nyx Scans",
            base_url="https://nyxscans.com",
            base_api_url="https://api.nyxscans.com",
        )

    @override
    async def initialize(self) -> None:
        await super().initialize()
        self.fetch_concurrency = 4
