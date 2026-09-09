import secrets


def generate_phone(index: int = 0) -> str:
    """Generate a unique 10-digit Indian mobile number starting with 9."""
    offset = secrets.randbelow(1_000_000_000)
    return f"9{offset:09d}"
