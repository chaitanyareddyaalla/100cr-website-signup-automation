import time


def generate_phone(index: int) -> str:
    """Generate a unique 10-digit Indian mobile number."""
    offset = (int(time.time() * 100) + index) % 1_000_000_000
    return f"9{offset:09d}"
