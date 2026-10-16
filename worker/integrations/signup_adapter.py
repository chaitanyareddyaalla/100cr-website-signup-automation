import json
import logging
import os
import threading
from typing import Protocol

try:
    from ..automation.browser_manager import BrowserManager
    from ..automation.device_manager import IsolatedDeviceTask
    from ..generators.test_data import TestIdentity
    from ..automation.signup_flow import SignupResult
except ImportError:
    from worker.automation.browser_manager import BrowserManager
    from worker.automation.device_manager import IsolatedDeviceTask
    from worker.generators.test_data import TestIdentity
    from worker.automation.signup_flow import SignupResult

logger = logging.getLogger(__name__)

_HTTP_POOL = None
_HTTP_POOL_LOCK = threading.Lock()

_DUPLICATE_MARKERS = (
    "already registered",
    "already exist",
    "already used",
    "phone number already",
    "phone already",
    "number already",
    "mobile already",
    "mobile number already",
    "user already",
    "account already",
    "duplicate entry",
    "duplicate phone",
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

            maxsize = max(1, min(int(os.getenv("MAX_PARALLEL_SIGNUPS", "15")), 50))
            read_timeout = float(os.getenv("SIGNUP_TIMEOUT_SECONDS", "10.0"))
            timeout = urllib3.Timeout(connect=3.0, read=read_timeout)
            proxy_url = os.getenv("ROTATING_PROXY_URL") or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
            if proxy_url:
                logger.info("Using configured proxy pool for signup adapter: %s", proxy_url.split("@")[-1])
                _HTTP_POOL = urllib3.ProxyManager(
                    proxy_url,
                    num_pools=8,
                    maxsize=maxsize,
                    timeout=timeout,
                    retries=False,
                )
            else:
                _HTTP_POOL = urllib3.PoolManager(
                    num_pools=8,
                    maxsize=maxsize,
                    timeout=timeout,
                    retries=False,
                )
        return _HTTP_POOL


class SignupAdapter(Protocol):
    def signup(self, identity: TestIdentity) -> SignupResult:
        ...


class AuthorizedPlaywrightAdapter:
    """Live automation adapter supporting direct API registration and isolated temporary Playwright device signups."""

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

    def _extract_clean_msg(self, body: str) -> str:
        clean_msg = body
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict) and "message" in parsed:
                clean_msg = str(parsed["message"])
        except Exception:
            pass
        return clean_msg

    def _api_signup(self, identity: TestIdentity) -> SignupResult:
        import time
        import urllib3

        safe_password = (identity.password or "").strip() or "SecurePass@123"
        safe_name = (identity.name or "").strip() or os.getenv("DEFAULT_STATIC_NAME", "Sreedhar Reddy")
        safe_place = (identity.place or "").strip() or os.getenv("DEFAULT_STATIC_PLACE", "Hyderabad")
        payload = json.dumps(
            {
                "name": safe_name,
                "phone": identity.phone,
                "place": safe_place,
                "password": safe_password,
                "referral_code": identity.referral,
            }
        ).encode("utf-8")

        endpoint = self.base_url if "api" in self.base_url else f"{self.base_url}/api/auth/signup"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://www.100crorescompany.com",
            "Referer": "https://www.100crorescompany.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "Connection": "keep-alive",
        }

        max_attempts = 3
        last_body = ""
        last_status = 0
        pool = _http_pool()

        for attempt in range(max_attempts):
            try:
                resp = pool.request(
                    "POST",
                    endpoint,
                    body=payload,
                    headers=headers,
                )
                last_status = resp.status
                last_body = (resp.data or b"").decode("utf-8", errors="replace")

                # Successful registration
                if 200 <= resp.status < 300:
                    return SignupResult.success(identity.account_id, phone=identity.phone)

                body_lower = last_body.lower()

                # If attempt > 0 and server says duplicate/already registered,
                # attempt 0 actually succeeded on the target server!
                if resp.status == 409 or any(marker in body_lower for marker in _DUPLICATE_MARKERS):
                    if attempt > 0:
                        logger.info("Signup verified for %s: confirmed registered on attempt %d", identity.phone, attempt + 1)
                        return SignupResult.success(identity.account_id, phone=identity.phone)
                    return SignupResult.duplicate(identity.account_id, phone=identity.phone)

                if any(marker in body_lower for marker in _LIMIT_MARKERS):
                    return SignupResult.limit_reached(
                        identity.account_id,
                        error=self._extract_clean_msg(last_body) or "Referral code maximum limit reached",
                        phone=identity.phone,
                    )

                if any(marker in body_lower for marker in _INVALID_REFERRAL_MARKERS):
                    return SignupResult(
                        account_id=identity.account_id,
                        status="INVALID_REFERRAL",
                        error=self._extract_clean_msg(last_body) or "Invalid referral code",
                        phone=identity.phone,
                    )

                # Transient errors: 429 rate limit or 5xx / 525 Cloudflare SSL handshake
                is_transient = (
                    resp.status == 429
                    or 500 <= resp.status < 600
                    or "error code: 525" in body_lower
                    or "ssl handshake failed" in body_lower
                    or "rate limit" in body_lower
                    or "too many requests" in body_lower
                )
                if is_transient and attempt < max_attempts - 1:
                    sleep_time = 0.25 * (attempt + 1)
                    time.sleep(sleep_time)
                    continue

                return self._classify_error_body(identity, last_body, http_status=resp.status)

            except (urllib3.exceptions.ConnectTimeoutError, urllib3.exceptions.ReadTimeoutError, urllib3.exceptions.TimeoutError):
                if attempt < max_attempts - 1:
                    time.sleep(0.25 * (attempt + 1))
                    continue
                return SignupResult(account_id=identity.account_id, status="TIMEOUT", error="TIMEOUT", phone=identity.phone)
            except Exception as exc:
                if attempt < max_attempts - 1:
                    time.sleep(0.25 * (attempt + 1))
                    continue
                return SignupResult.failure(identity.account_id, error=str(exc), phone=identity.phone)

        return self._classify_error_body(identity, last_body, http_status=last_status)

    def _classify_error_body(self, identity: TestIdentity, body: str, http_status: int = 0) -> SignupResult:
        body_lower = (body or "").lower()
        clean_msg = self._extract_clean_msg(body)

        # 5xx / Cloudflare errors must be classified as SERVER_ERROR first, never as DUPLICATE or SKIPPED
        if 500 <= http_status < 600 or "error code: 525" in body_lower or "ssl handshake failed" in body_lower:
            return SignupResult(
                account_id=identity.account_id,
                status="SERVER_ERROR",
                error=clean_msg or f"Server error {http_status}",
                phone=identity.phone,
            )
        if http_status == 429 or "too many requests" in body_lower or "rate limit" in body_lower:
            return SignupResult(
                account_id=identity.account_id,
                status="RATE_LIMITED",
                error=clean_msg or "Rate limited (HTTP 429)",
                phone=identity.phone,
            )
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
        return SignupResult.failure(identity.account_id, error=clean_msg or f"HTTP {http_status}", phone=identity.phone)

    def _browser_signup(self, identity: TestIdentity) -> SignupResult:
        signup_url = os.getenv("SIGNUP_PAGE_URL", "https://www.100crorescompany.com/signup")
        safe_name = (identity.name or "").strip() or os.getenv("DEFAULT_STATIC_NAME", "Sreedhar Reddy")
        safe_place = (identity.place or "").strip() or os.getenv("DEFAULT_STATIC_PLACE", "Hyderabad")
        safe_password = (identity.password or "").strip() or "SecurePass@123"
        try:
            with IsolatedDeviceTask(timeout_ms=self.timeout_ms) as device:
                page = device.page
                page.goto(signup_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                page.fill("#name", safe_name)
                page.fill("#phone", identity.phone)
                page.fill("#place", safe_place)
                page.fill("#password", safe_password)
                page.fill("#referralCode", identity.referral)
                page.click("button[type='submit']")
                page.wait_for_timeout(2000)
                return SignupResult.success(identity.account_id, phone=identity.phone)
        except Exception as exc:
            err_str = str(exc)
            if "Timeout" in type(exc).__name__ or "timeout" in err_str.lower():
                return SignupResult(account_id=identity.account_id, status="TIMEOUT", error="TIMEOUT", phone=identity.phone)
            return SignupResult.failure(identity.account_id, error=f"SITE_ERROR: {exc}", phone=identity.phone)
