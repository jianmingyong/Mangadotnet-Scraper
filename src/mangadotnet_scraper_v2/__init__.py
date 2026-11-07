from mangadotnet_scraper_v2.config import Config
from mangadotnet_scraper_v2.config.providers import JsonConfigProvider


def initialize() -> None:
    config = Config(JsonConfigProvider("config_test.json"))
    config.load()
