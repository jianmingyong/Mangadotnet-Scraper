from mangadotnet_scraper.config import ConfigProvider
from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates.ezmanhwa import EzManhwaTemplate


class EzMangaSourceProvider(EzManhwaTemplate):
    def __init__(self, config: ConfigProvider) -> None:
        super().__init__(
            config,
            group_name="Ezmanga",
            source_id="en.ez_manga",
            name="Ez Manga",
            version=1,
            languages=["en"],
            base_url="https://ezmanga.org",
            base_api_url="https://vapi.ezmanga.org",
        )


SourceProvider.register_source(EzMangaSourceProvider)
