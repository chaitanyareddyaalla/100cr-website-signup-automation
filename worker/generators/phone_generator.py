import secrets


def generate_phone(index: int = 0) -> str:
    """Generate 10-digit numbers across all 10 billion combinations (0000000000 through 9999999999).

    Supports any digit (0-9) at any position across all 10,000,000,000 possible combinations.
    """
    return f"{secrets.randbelow(10_000_000_000):010d}"



