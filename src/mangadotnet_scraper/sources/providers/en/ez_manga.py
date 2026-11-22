from mangadotnet_scraper.sources import SourceProvider
from mangadotnet_scraper.sources.templates.ezmanhwa import EzManhwaTemplate


class EzMangaSourceProvider(EzManhwaTemplate):
    def __init__(self, **kwargs) -> None:
        super().__init__(
            group_name="Ezmanga",
            source_id="en.ez_manga",
            name="Ez Manga",
            version=1,
            languages=["en"],
            base_url="https://ezmanga.org",
            base_api_url="https://vapi.ezmanga.org",
            **kwargs,
        )


SourceProvider.register_source(EzMangaSourceProvider)
