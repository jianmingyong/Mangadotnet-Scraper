import logging
import sys
from typing import Literal, cast

from camoufox import AsyncCamoufox
from playwright.async_api import Browser, Error, Page, Response
from playwright_captcha import CaptchaType, ClickSolver, FrameworkType
from playwright_captcha.utils.camoufox_add_init_script.add_init_script import (
    get_addon_path,
)
from playwright_captcha.utils.exceptions import (
    CaptchaDetectionError,
    CaptchaSolvingError,
)


def create_browser(
    headless: bool | str = True, **launch_options
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


async def handle_cloudflare_interstitial(
    page: Page,
    url: str,
    wait_until: Literal["domcontentloaded", "load", "networkidle"]
    | None = None,
    expected_content_selector: str | None = None,
) -> Response:
    async with ClickSolver(
        framework=FrameworkType.CAMOUFOX, page=page
    ) as solver:
        response = cast(Response, await page.goto(url))

        if await response.header_value("cf-mitigated") == "challenge":
            await solver.solve_captcha(
                captcha_container=page,
                captcha_type=CaptchaType.CLOUDFLARE_INTERSTITIAL,
                expected_content_selector=expected_content_selector,
            )

            await page.wait_for_load_state(wait_until)

        return response


async def get_cloudflare_cookies(
    url: str, user_agent: str | None = None
) -> tuple[str, str] | None:
    try:
        async with (
            create_browser() as browser,
            await cast(Browser, browser).new_context(
                user_agent=user_agent
            ) as context,
        ):
            page = await context.new_page()

            try:
                response = await handle_cloudflare_interstitial(
                    page, url, "domcontentloaded"
                )
            except CaptchaDetectionError, CaptchaSolvingError:
                logging.getLogger(__name__).exception(
                    "Failed to solve cloudflare captcha"
                )
                return None

            if not response.ok and await response.header_value("cf-mitigated") != "challenge":
                logging.getLogger(__name__).error(
                    f"Failed to get cloudflare cookies due to request {response.status} ({response.status_text}) from {url}"
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

        return user_agent, cookie_value
    except Error:
        logging.getLogger(__name__).exception(
            "Failed to get cloudflare cookies due to camoufox error"
        )
        return None
