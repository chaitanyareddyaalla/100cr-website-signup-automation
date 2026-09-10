import secrets


def generate_phone(index: int = 0) -> str:
    """Generate 10-digit numbers starting with any digit from 0 to 9.

    Covers all 10 billion possible combinations (0000000000 through 9999999999),
    allowing rapid signups with full digit variety (e.g., 0xxxxxxxxx, 1xxxxxxxxx, 2222222222, etc.).
    """
    return f"{secrets.randbelow(10_000_000_000):010d}"

