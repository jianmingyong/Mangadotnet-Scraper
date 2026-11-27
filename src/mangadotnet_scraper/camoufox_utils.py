import asyncio
import sys
from asyncio import create_task, sleep, wait
from contextlib import AbstractAsyncContextManager
from typing import Literal, Self, cast, override

from camoufox import AsyncCamoufox
from playwright.async_api import Browser as PlaywrightBrowser
from playwright.async_api import (
    BrowserContext,
    Page,
    Response,
)
from playwright_captcha import CaptchaType, ClickSolver
from playwright_captcha.utils.camoufox_add_init_script.add_init_script import (
    get_addon_path,
)


class Browser(AbstractAsyncContextManager):
    _browser: PlaywrightBrowser
    _browser_context: BrowserContext

    user_agent: str

    @override
    async def __aenter__(self) -> Self:
        await self.initialize()
        return self

    @override
    async def __aexit__(self, *args) -> None:
        await self.close()

    async def initialize(self) -> None:
        self._browser = cast(PlaywrightBrowser, await create_browser().start())
        self._browser_context = await self.new_context()

        async with await self._browser_context.new_page() as page:
            self.user_agent = await page.evaluate("navigator.userAgent")

    async def close(self) -> None:
        await self._browser_context.close()
        await self._browser.close()

    async def new_context(
        self,
        user_agent: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> BrowserContext:
        return await self._browser.new_context(
            user_agent=user_agent, base_url=base_url, **kwargs
        )

    async def get_shared_context(self) -> BrowserContext:
        if self._browser_context.is_closed():
            self._browser_context = await self.new_context()

        return self._browser_context

    async def get_shared_context_page(self) -> Page:
        if self._browser_context.is_closed():
            self._browser_context = await self.new_context()

        return await self._browser_context.new_page()


def create_browser(
    headless: bool | Literal["virtual"] = True, **launch_options
) -> AsyncCamoufox:
    os = sys.platform

    if os == "win32" or os == "cygwin":
        os = "windows"
    elif os == "linux":
        os = "linux"
    elif os == "darwin":
        os = "macos"

    return AsyncCamoufox(
        headless=headless,
        os=os,
        locale="en-US",
        humanize=True,
        i_know_what_im_doing=True,
        config={"forceScopeAccess": True},
        disable_coop=True,
        main_world_eval=True,
        addons=[get_addon_path()],
        **launch_options,
    )


async def solve_cloudflare_captcha_interstitial(
    solver: ClickSolver, page: Page, response: Response
) -> bool:
    async def wait_until_cloudflare_solved() -> None:
        locator = page.locator(
            'head > script[src^="https://challenges.cloudflare.com/turnstile/"]'
        )

        while not page.is_closed() and await locator.count() > 0:
            script_src = await locator.get_attribute("src")

            if script_src is not None and script_src.startswith(
                "https://challenges.cloudflare.com/turnstile/v0/api.js"
            ):
                # This is a different turnstile so we can assume that it is already loaded.
                break

            await sleep(1)

    async def run_solve_cloudflare_captcha() -> None:
        await solver.solve_captcha(
            captcha_container=page,
            captcha_type=CaptchaType.CLOUDFLARE_INTERSTITIAL,
        )

    if await response.header_value("cf-mitigated") == "challenge":
        task = create_task(wait_until_cloudflare_solved())
        task2 = create_task(run_solve_cloudflare_captcha())

        await wait([task, task2], return_when=asyncio.FIRST_COMPLETED)

        if task2.done():
            await wait(task, timeout=30)

        if task2.done() and task2.exception():
            return False

        if task.done():
            task2.cancel()

    return True


async def solve_cloudflare_captcha_turnstile(
    solver: ClickSolver,
    page: Page,
    expected_content_selector: str,
) -> bool:
    async def wait_until_cloudflare_solved() -> None:
        locator = page.locator('input[name="cf-turnstile-response"]')

        while await locator.count() == 0:
            await sleep(1)

        while True:
            if await locator.input_value() != "":
                break

            await sleep(1)

    async def run_solve_cloudflare_captcha() -> None:
        await solver.solve_captcha(
            captcha_container=page,
            captcha_type=CaptchaType.CLOUDFLARE_TURNSTILE,
            expected_content_selector=expected_content_selector,
        )

    task = create_task(wait_until_cloudflare_solved())
    task2 = create_task(run_solve_cloudflare_captcha())

    await wait([task, task2], return_when=asyncio.FIRST_COMPLETED)

    if task2.done():
        await wait(task, timeout=30)

    if task2.done() and task2.exception():
        return False

    if task.done():
        task2.cancel()

    return True
