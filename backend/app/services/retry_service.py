"""Retry policy for transient automation failures."""

import random

RETRYABLE_ERRORS = {"NETWORK_ERROR", "TIMEOUT", "SERVER_ERROR"}


def retry_delay(attempt: int, base_seconds: float = 2.0, cap_seconds: float = 60.0) -> float:
    """Exponential backoff with a small bounded jitter."""
    if attempt < 1:
        return 0.0
    return min(cap_seconds, base_seconds * (2 ** (attempt - 1))) + random.uniform(0, 0.25)


def is_retryable(error_type: str) -> bool:
    return error_type in RETRYABLE_ERRORS
