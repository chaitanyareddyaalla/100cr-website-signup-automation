"""Isolated and temporary multi-device browser management for low-memory environments."""

from __future__ import annotations

import gc
import logging
import os
import random
import shutil
import tempfile
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeviceProfile:
    name: str
    user_agent: str
    viewport: dict[str, int]
    is_mobile: bool
    has_touch: bool


DEVICE_PROFILES: tuple[DeviceProfile, ...] = (
    DeviceProfile(
        name="Pixel 7",
        user_agent=(
            "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        ),
        viewport={"width": 412, "height": 915},
        is_mobile=True,
        has_touch=True,
    ),
    DeviceProfile(
        name="Samsung Galaxy S23",
        user_agent=(
            "Mozilla/5.0 (Linux; Android 13; SM-S911B) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36"
        ),
        viewport={"width": 393, "height": 851},
        is_mobile=True,
        has_touch=True,
    ),
    DeviceProfile(
        name="iPhone 14",
        user_agent=(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1"
        ),
        viewport={"width": 390, "height": 844},
        is_mobile=True,
        has_touch=True,
    ),
    DeviceProfile(
        name="Desktop Chrome",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
        is_mobile=False,
        has_touch=False,
    ),
)

# Ultra-lean flags to keep Chromium memory usage strictly bounded in 512MB containers
LEAN_CHROMIUM_FLAGS: tuple[str, ...] = (
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-breakpad",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-domain-reliability",
    "--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process",
    "--disable-hang-monitor",
    "--disable-ipc-flooding-protection",
    "--disable-popup-blocking",
    "--disable-prompt-on-repost",
    "--disable-renderer-backgrounding",
    "--disable-sync",
    "--disable-translate",
    "--metrics-recording-only",
    "--no-first-run",
    "--safebrowsing-disable-auto-update",
    "--password-store=basic",
    "--use-mock-keychain",
    "--mute-audio",
    "--js-flags=--max-old-space-size=64",
)


def trim_system_memory() -> None:
    """Trigger Python GC and instruct glibc to release unused heap arenas back to the OS."""
    try:
        gc.collect()
        if hasattr(os, "uname") and os.uname().sysname == "Linux":
            try:
                import ctypes
                ctypes.CDLL("libc.so.6").malloc_trim(0)
            except Exception:
                pass
    except Exception:
        pass


class IsolatedDeviceTask:
    """Isolated, temporary multi-device browser session.
    
    Creates a temporary browser/context/page exclusively for a single referral task,
    then unconditionally tears down the browser and deletes all temporary files/caches on exit.
    """

    def __init__(self, timeout_ms: int = 15_000, device_profile: DeviceProfile | None = None) -> None:
        self.timeout_ms = timeout_ms
        self.profile = device_profile or random.choice(DEVICE_PROFILES)
        self.temp_dir: str | None = None
        self._playwright: Any = None
        self.browser: Any = None
        self.context: Any = None
        self.page: Any = None

    def __enter__(self) -> IsolatedDeviceTask:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Playwright is not installed for browser automation") from exc

        # Create isolated temporary directory for this specific task
        self.temp_dir = tempfile.mkdtemp(prefix="render_device_")

        try:
            self._playwright = sync_playwright().start()
            self.browser = self._playwright.chromium.launch(
                headless=True,
                args=[*LEAN_CHROMIUM_FLAGS, f"--user-data-dir={self.temp_dir}"],
            )
            self.context = self.browser.new_context(
                user_agent=self.profile.user_agent,
                viewport=self.profile.viewport,
                is_mobile=self.profile.is_mobile,
                has_touch=self.profile.has_touch,
                accept_downloads=False,
                service_workers="block",
            )
            self.page = self.context.new_page()
            self.page.set_default_timeout(self.timeout_ms)

            # Block heavy media, images, and webfonts to slash Chromium RAM usage by 60-80%
            self.page.route(
                "**/*.{png,jpg,jpeg,webp,gif,svg,ico,woff,woff2,ttf,eot,mp4,webm,avi,mp3,wav}",
                lambda route: route.abort(),
            )
            return self
        except Exception:
            self._cleanup()
            raise

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self._cleanup()

    def _cleanup(self) -> None:
        """Immediately close page, context, browser and purge all temporary files."""
        if self.page is not None:
            try:
                self.page.close()
            except Exception:
                pass
            self.page = None

        if self.context is not None:
            try:
                self.context.close()
            except Exception:
                pass
            self.context = None

        if self.browser is not None:
            try:
                self.browser.close()
            except Exception:
                pass
            self.browser = None

        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except Exception as exc:
                logger.warning(f"Could not remove temporary directory {self.temp_dir}: {exc}")
            self.temp_dir = None

        # Immediate memory reclamation
        trim_system_memory()
