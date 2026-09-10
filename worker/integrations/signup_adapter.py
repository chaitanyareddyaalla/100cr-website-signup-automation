import json
import logging
import os
import threading
from typing import Protocol

try:
    from ..automation.browser_manager import BrowserManager
    from ..generators.test_data import TestIdentity
    from ..automation.signup_flow import SignupResult
except ImportError:
    from automation.browser_manager import BrowserManager
    from generators.test_data import TestIdentity
    from automation.signup_flow import SignupResult

logger = logging.getLogger(__name__)

_HTTP_POOL = None
_HTTP_POOL_LOCK = threading.Lock()

_DUPLICATE_MARKERS = (
    "already registered",
    "already exist",
    "already used",
    "phone already",
    "number already",
    "duplicate",
)
_LIMIT_MARKERS = (
    "maximum limit",
    "reached its maximum",
    "referral code has reached",
    "limit reached",
)
_INVALID_REFERRAL_MARKERS = (
    "invalid referral",
    "referral code not found",
    "referral not found",
    "invalid code",
)


def _http_pool():
    global _HTTP_POOL
    with _HTTP_POOL_LOCK:
        if _HTTP_POOL is None:
            import urllib3

            maxsize = max(1, int(os.getenv("MAX_PARALLEL_SIGNUPS", "100")))
            _HTTP_POOL = urllib3.PoolManager(
                num_pools=8,
                maxsize=maxsize,
                timeout=urllib3.Timeout(connect=10.0, read=15.0),
                retries=False,
            )
        return _HTTP_POOL


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
        self.base_url = (
            base_url or os.getenv("AUTHORIZED_TEST_BASE_URL", "https://api.universalcompanys.com/api/auth/signup")
        ).rstrip("/")
        self.timeout_ms = timeout_ms

    def signup(self, identity: TestIdentity) -> SignupResult:
        use_browser = os.getenv("USE_BROWSER", "false").lower() in ("true", "1")
        if use_browser:
            return self._browser_signup(identity)
        return self._api_signup(identity)

    def _api_signup(self, identity: TestIdentity) -> SignupResult:
        import urllib3

        payload = json.dumps(
            {
                "name": identity.name or "Chaitanya Reddy",
                "phone": identity.phone,
                "place": identity.place or "Hyderabad",
                "password": identity.password or "SecurePass@123",
                "referral_code": identity.referral,
            }
        ).encode("utf-8")

        endpoint = self.base_url if "api" in self.base_url else f"{self.base_url}/api/auth/signup"
        try:
            resp = _http_pool().request(
                "POST",
                endpoint,
                body=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
            )
            if 200 <= resp.status < 300:
                return SignupResult.success(identity.account_id, phone=identity.phone)
            body = (resp.data or b"").decode("utf-8", errors="replace")
            return self._classify_error_body(identity, body, http_status=resp.status)
        except (urllib3.exceptions.ConnectTimeoutError, urllib3.exceptions.ReadTimeoutError, urllib3.exceptions.TimeoutError):
            return SignupResult(account_id=identity.account_id, status="TIMEOUT", error="TIMEOUT", phone=identity.phone)
        except Exception as exc:
            return SignupResult.failure(identity.account_id, error=str(exc), phone=identity.phone)

    def _classify_error_body(self, identity: TestIdentity, body: str, http_status: int = 0) -> SignupResult:
        body_lower = (body or "").lower()
        clean_msg = body
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict) and "message" in parsed:
                clean_msg = str(parsed["message"])
        except Exception:
            pass

        if http_status == 409 or any(marker in body_lower for marker in _DUPLICATE_MARKERS):
            return SignupResult.duplicate(identity.account_id, phone=identity.phone)
        if any(marker in body_lower for marker in _LIMIT_MARKERS):
            return SignupResult.limit_reached(
                identity.account_id,
                error=clean_msg or "Referral code maximum limit reached",
                phone=identity.phone,
            )
        if any(marker in body_lower for marker in _INVALID_REFERRAL_MARKERS):
            return SignupResult(
                account_id=identity.account_id,
                status="INVALID_REFERRAL",
                error=clean_msg or "Invalid referral code",
                phone=identity.phone,
            )
        if 500 <= http_status < 600:
            return SignupResult(
                account_id=identity.account_id,
                status="SERVER_ERROR",
                error=clean_msg or f"Server error {http_status}",
                phone=identity.phone,
            )
        return SignupResult.failure(identity.account_id, error=clean_msg or f"HTTP {http_status}", phone=identity.phone)

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
            return SignupResult(account_id=identity.account_id, status="TIMEOUT", error="TIMEOUT", phone=identity.phone)
        except Exception as exc:
            return SignupResult.failure(identity.account_id, error=f"SITE_ERROR: {exc}", phone=identity.phone)
