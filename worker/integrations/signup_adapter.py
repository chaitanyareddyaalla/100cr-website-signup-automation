import os
from typing import Protocol
from urllib.parse import urlparse

try:
    from ..automation.browser_manager import BrowserManager
    from ..generators.test_data import TestIdentity
    from ..automation.signup_flow import SignupResult
except ImportError:
    from automation.browser_manager import BrowserManager
    from generators.test_data import TestIdentity
    from automation.signup_flow import SignupResult


class SignupAdapter(Protocol):
    def signup(self, identity: TestIdentity) -> SignupResult:
        ...


class MockSignupAdapter:
    def signup(self, identity: TestIdentity) -> SignupResult:
        with BrowserManager():
            return SignupResult.success(identity.account_id)


class AuthorizedPlaywrightAdapter:
    """Live automation adapter supporting direct API registration and Playwright browser signup."""

    def __init__(self, base_url: str | None = None, timeout_ms: int = 15_000) -> None:
        self.base_url = (base_url or os.getenv("AUTHORIZED_TEST_BASE_URL", "https://api.universalcompanys.com/api/auth/signup")).rstrip("/")
        self.timeout_ms = timeout_ms

    def signup(self, identity: TestIdentity) -> SignupResult:
        use_browser = os.getenv("USE_BROWSER", "false").lower() in ("true", "1")
        if use_browser:
            return self._browser_signup(identity)
        return self._api_signup(identity)

    def _api_signup(self, identity: TestIdentity) -> SignupResult:
        import json
        import urllib.error
        import urllib.request

        payload = {
            "name": identity.name or "Chaitanya Reddy",
            "phone": identity.phone,
            "place": identity.place or "Hyderabad",
            "password": identity.password or "SecurePass@123",
            "referral_code": identity.referral,
        }

        endpoint = self.base_url if "api" in self.base_url else f"{self.base_url}/api/auth/signup"
        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout_ms / 1000.0) as resp:
                resp.read().decode("utf-8", errors="replace")
                return SignupResult.success(identity.account_id, phone=identity.phone)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if "already registered" in body.lower():
                return SignupResult.duplicate(identity.account_id, phone=identity.phone)
            return SignupResult.failure(identity.account_id, error=body or str(exc), phone=identity.phone)
        except Exception as exc:
            return SignupResult.failure(identity.account_id, error=str(exc), phone=identity.phone)

    def _browser_signup(self, identity: TestIdentity) -> SignupResult:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
        except ImportError as exc:
            raise RuntimeError("Install Playwright before enabling browser automation") from exc

        signup_url = os.getenv("SIGNUP_PAGE_URL", "https://www.100crorescompany.com/signup")
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                try:
                    page = context.new_page()
                    page.set_default_timeout(self.timeout_ms)
                    page.goto(signup_url, wait_until="networkidle", timeout=self.timeout_ms)
                    page.fill("#name", identity.name or "Chaitanya Reddy")
                    page.fill("#phone", identity.phone)
                    page.fill("#place", identity.place or "Hyderabad")
                    page.fill("#password", identity.password or "SecurePass@123")
                    page.fill("#referralCode", identity.referral)
                    page.click("button[type='submit']")
                    page.wait_for_timeout(2000)
                    return SignupResult.success(identity.account_id, phone=identity.phone)
                finally:
                    context.close()
                    browser.close()
        except PlaywrightTimeoutError:
            return SignupResult.failure(identity.account_id, "TIMEOUT", phone=identity.phone)
        except Exception as exc:
            return SignupResult.failure(identity.account_id, f"SITE_ERROR: {exc}", phone=identity.phone)
