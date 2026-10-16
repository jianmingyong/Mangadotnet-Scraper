from mangadotnet_scraper.config import MangaDotNetScraperConfig
from mangadotnet_scraper.modules.templates.ezmanhwa import EzManhwaTemplate


class EzMangaModule(EzManhwaTemplate):
    def __init__(self, config: MangaDotNetScraperConfig) -> None:
        super().__init__(
            config,
            group_name="Ezmanga",
            module_id="ez_manga",
            display_name="Ez Manga",
            language="en",
            version=1,
            base_url="https://ezmanga.org",
            base_api_url="https://vapi.ezmanga.org",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0",
        )
