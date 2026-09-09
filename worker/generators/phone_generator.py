import secrets

# Authentic Indian mobile operator series (Airtel, Jio, Vodafone-Idea, BSNL)
VALID_INDIAN_PREFIXES = [
    # 9-series
    "90", "91", "92", "93", "94", "95", "96", "97", "98", "99",
    # 8-series
    "80", "81", "82", "83", "84", "85", "86", "87", "88", "89",
    # 7-series
    "70", "72", "73", "74", "75", "76", "77", "78", "79",
    # 6-series
    "62", "63", "69",
]


def generate_phone(index: int = 0) -> str:
    """Generate diverse combinations of valid 10-digit Indian mobile numbers.

    Uses authentic Indian mobile operator series (9x, 8x, 7x, 6x) with random suffix digits.
    """
    prefix = secrets.choice(VALID_INDIAN_PREFIXES)
    remaining_digits = secrets.randbelow(100_000_000)
    return f"{prefix}{remaining_digits:08d}"

