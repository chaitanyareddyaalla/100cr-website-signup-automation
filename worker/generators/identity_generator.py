try:
    from .phone_generator import generate_phone
    from .test_data import TestIdentity
except ImportError:
    from generators.phone_generator import generate_phone
    from generators.test_data import TestIdentity


def generate_test_identity(index: int) -> TestIdentity:
    return TestIdentity(
        account_id=f"TEST{index:03d}",
        name=f"Test User {index}",
        test_id=f"ident-{index:04d}",
        phone=generate_phone(index),
    )


def generate_identity_with_phone(index: int) -> tuple[TestIdentity, str]:
    return generate_test_identity(index), generate_phone(index)
