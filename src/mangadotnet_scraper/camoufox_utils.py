import logging
import sys
from typing import cast

from camoufox import AsyncCamoufox
from playwright.async_api import Browser, Error
from playwright_captcha import CaptchaType, ClickSolver, FrameworkType
from playwright_captcha.utils.camoufox_add_init_script.add_init_script import (
    get_addon_path,
)
from playwright_captcha.utils.exceptions import (
    CaptchaApplyingError,
    CaptchaDataDetectionError,
    CaptchaDetectionError,
    CaptchaSolvingError,
)


def create_browser(headless: bool | str = True, **launch_options) -> AsyncCamoufox:
    os = sys.platform

    if os == "win32" or os == "cygwin":
        os = "windows"
    elif os == "linux":
        os = "linux"
    elif os == "darwin":
        os = "macos"

    # if os == "linux" and headless:
    #    headless = "virtual"

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


async def get_cloudflare_cookies(url: str, user_agent: str | None = None) -> tuple[str, str] | None:
    try:
        async with (
            create_browser() as browser,
            await cast(Browser, browser).new_context(user_agent=user_agent) as context,
        ):
            page = await context.new_page()

            async with ClickSolver(framework=FrameworkType.CAMOUFOX, page=page) as solver:
                await page.goto(url, wait_until="domcontentloaded")

                if user_agent is None:
                    user_agent = await page.evaluate("navigator.userAgent")

                try:
                    await page.wait_for_selector('input[name="cf-turnstile-response"]', state="hidden")
                except TimeoutError:
                    logging.getLogger(__name__).exception("Cloudflare captcha does not exists")
                    return None

                try:
                    await solver.solve_captcha(
                        captcha_container=page,
                        captcha_type=CaptchaType.CLOUDFLARE_INTERSTITIAL,
                    )
                except (
                    CaptchaDetectionError,
                    CaptchaDataDetectionError,
                    CaptchaSolvingError,
                    CaptchaApplyingError,
                ):
                    logging.getLogger(__name__).exception("Failed to solve Cloudflare captcha")
                    return None

                await page.wait_for_load_state("domcontentloaded")

            cookies = await context.cookies(url)
            cookie_value = None

            for cookie in cookies:
                if cookie.get("name") == "cf_clearance":
                    cookie_value = cookie.get("value")
                    break

            if cookie_value is None:
                return None

        return user_agent, cookie_value
    except Error:
        logging.getLogger(__name__).exception("Camoufox crashed")
        return None
