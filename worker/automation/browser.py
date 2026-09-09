"""Browser boundary for the authorized mock worker.

Real third-party account creation is deliberately not implemented.
"""


def open_authorized_test_site() -> None:
    raise NotImplementedError("Use the local mock signup flow for development")
