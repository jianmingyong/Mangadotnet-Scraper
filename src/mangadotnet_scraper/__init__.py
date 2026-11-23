import asyncio
import logging
import sys

if sys.platform == "linux":
    import uvloop

from mangadotnet_scraper.app import App


def initialize() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        filename="mangadotnet_scraper.log",
        encoding="utf-8",
    )
    logging.getLogger("peewee").setLevel(logging.INFO)

    try:
        if sys.platform == "linux":
            uvloop.run(initialize_app())
        else:
            asyncio.run(initialize_app())
    except Exception:
        logging.getLogger(__name__).exception("Unhandled exception caught")
        raise


async def initialize_app() -> None:
    async with App() as app:
        await app.run()
