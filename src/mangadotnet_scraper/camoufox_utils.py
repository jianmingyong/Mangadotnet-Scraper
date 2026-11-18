import asyncio
import logging
import sys
from asyncio import create_task, sleep, wait
from typing import Literal, cast

from camoufox import AsyncCamoufox
from playwright.async_api import Browser, Error, Page, Response, TimeoutError
from playwright_captcha import CaptchaType, ClickSolver, FrameworkType
from playwright_captcha.utils.camoufox_add_init_script.add_init_script import (
    get_addon_path,
)


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


async def get_default_user_agent() -> str | None:
    try:
        async with (
            create_browser() as browser,
            await cast(Browser, browser).new_context() as context,
        ):
            page = await context.new_page()
            return await page.evaluate("navigator.userAgent")
    except Error:
        logging.getLogger(__name__).exception(
            "[Camoufox] Failed to get user agent due to camoufox error"
        )
        return None


async def solve_cloudflare_captcha_interstitial(
    solver: ClickSolver, page: Page, response: Response
) -> bool:
    async def wait_until_cloudflare_solved() -> None:
        locator = page.locator(
            'head > script[src^="https://challenges.cloudflare.com/turnstile/"]'
        )

        while await locator.count() > 0:
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
            task.cancel()

        if task2.done() and not task2.cancelled() and task2.exception():
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
            try:
                if await locator.input_value(timeout=1000) != "":
                    break
            except TimeoutError:
                pass

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
        task.cancel()

    if task2.done() and not task2.cancelled() and task2.exception():
        return False

    if task.done():
        task2.cancel()

    return True


async def get_cloudflare_cookies(
    url: str, user_agent: str | None = None
) -> tuple[str, str] | None:
    try:
        async with (
            create_browser() as browser,
            await cast(Browser, browser).new_context(
                user_agent=user_agent
            ) as context,
            await context.new_page() as page,
            ClickSolver(framework=FrameworkType.CAMOUFOX, page=page) as solver,
        ):
            response = cast(Response, await page.goto(url))

            if not await solve_cloudflare_captcha_interstitial(
                solver, page, response
            ):
                logging.getLogger(__name__).error(
                    "[Camoufox] Failed to solve cloudflare captcha"
                )
                return None

            if user_agent is None:
                user_agent = await page.evaluate("navigator.userAgent")

            cookies = await context.cookies(url)
            cookie_value = None

            for cookie in cookies:
                if cookie.get("name") == "cf_clearance":
                    cookie_value = cookie.get("value")
                    break

            if cookie_value is None:
                return None

        logging.getLogger(__name__).debug(
            "[Camoufox] Cloudflare cookies obtained for user agent (%s): %s",
            user_agent,
            cookie_value,
        )

        return user_agent, cookie_value
    except Error:
        logging.getLogger(__name__).exception(
            "[Camoufox] Failed to get cloudflare cookies due to camoufox error"
        )
        return None
