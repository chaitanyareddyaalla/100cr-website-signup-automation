from contextlib import AbstractContextManager
from typing import Any


class BrowserManager(AbstractContextManager["BrowserManager"]):
    def __init__(self) -> None:
        self.browser: Any = None
        self.closed = False

    def __enter__(self) -> "BrowserManager":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        browser = self.browser
        if browser is not None and hasattr(browser, "close"):
            browser.close()
