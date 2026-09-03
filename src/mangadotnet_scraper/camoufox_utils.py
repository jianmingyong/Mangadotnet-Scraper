import sys

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


def create_browser(headless=True, **launch_options):
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


async def get_cloudflare_cookies(url: str) -> tuple[str, str] | None:
    try:
        async with create_browser() as browser:
            assert isinstance(browser, Browser), "Browser is not an instance of playwright.async_api.Browser"
            context = await browser.new_context()
            page = await context.new_page()

            async with ClickSolver(framework=FrameworkType.CAMOUFOX, page=page) as solver:
                await page.goto(url, wait_until="domcontentloaded")
                user_agent: str = await page.evaluate("navigator.userAgent")

                await page.wait_for_selector('input[name="cf-turnstile-response"]', state="hidden")

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
                    # Unable to solve cloudflare captcha
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
        return None
