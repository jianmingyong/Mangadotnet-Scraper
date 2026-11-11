from mangadotnet_scraper.config import Config
from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates.ezmanhwa import EzManhwaTemplate


class EzMangaSourceProvider(EzManhwaTemplate):
    def __init__(self, config: Config) -> None:
        super().__init__(
            config,
            group_name="Ezmanga",
            base_api_url="https://vapi.ezmanga.org",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:159.0) Gecko/20100101 Firefox/159.0",
            source_id="en.ez_manga",
            name="Ez Manga",
            version=1,
            languages=["en"],
            base_url="https://ezmanga.org",
        )


SourceProvider.register_source(EzMangaSourceProvider)
