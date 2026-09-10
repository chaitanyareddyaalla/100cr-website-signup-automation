import secrets

# Known dummy/bot repetitive patterns that result in instant collisions / duplicate errors on target sites
EXCLUDED_PATTERNS = {
    "1234567890", "0123456789", "9876543210", "1111111111",
    "2222222222", "3333333333", "4444444444", "5555555555",
    "6666666666", "7777777777", "8888888888", "9999999999",
    "0000000000", "0000000001", "1000000000", "9000000000",
}


def generate_phone(index: int = 0) -> str:
    """Generate high-entropy 10-digit numbers across all 10 billion combinations (0-9).

    Filters out repetitive dummy patterns to minimize duplicate collisions and prevent skips.
    """
    for _ in range(10):
        candidate = f"{secrets.randbelow(10_000_000_000):010d}"
        if (
            candidate not in EXCLUDED_PATTERNS
            and not candidate.startswith(("000", "111", "222", "333", "444", "555", "666", "777", "888", "999"))
        ):
            return candidate
    return f"{secrets.randbelow(10_000_000_000):010d}"

