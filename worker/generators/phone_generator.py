import secrets

# Authentic Indian mobile operator series (Airtel, Jio, Vodafone-Idea, BSNL)
VALID_INDIAN_PREFIXES = [
    # 9-series
    "90", "91", "92", "93", "94", "95", "96", "97", "98", "99",
    # 8-series
    "80", "81", "82", "83", "84", "85", "86", "87", "88", "89",
    # 7-series
    "70", "71", "72", "73", "74", "75", "76", "77", "78", "79",
    # 6-series
    "62", "63", "64", "65", "66", "67", "68", "69",
]

# Known dummy/bot repetitive patterns that result in instant collisions / duplicate errors on target sites
EXCLUDED_PATTERNS = {
    "12345678", "87654321", "00000000", "11111111", "22222222",
    "33333333", "44444444", "55555555", "66666666", "77777777",
    "88888888", "99999999", "01234567",
}


def generate_phone(index: int = 0) -> str:
    """Generate high-entropy, realistic 10-digit Indian mobile numbers (9x, 8x, 7x, 6x).

    Uses authentic Indian mobile operator series with random suffix digits,
    filtering out repetitive dummy patterns to avoid duplicate collisions and prevent skips.
    """
    for _ in range(10):
        prefix = secrets.choice(VALID_INDIAN_PREFIXES)
        suffix = f"{secrets.randbelow(100_000_000):08d}"
        if (
            suffix not in EXCLUDED_PATTERNS
            and not suffix.startswith(("000", "111", "222", "333", "444", "555", "666", "777", "888", "999"))
        ):
            return f"{prefix}{suffix}"
    prefix = secrets.choice(VALID_INDIAN_PREFIXES)
    return f"{prefix}{secrets.randbelow(100_000_000):08d}"


