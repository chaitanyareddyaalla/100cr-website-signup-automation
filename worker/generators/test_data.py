import os
from dataclasses import dataclass

try:
    from .phone_generator import generate_phone
except ImportError:
    try:
        from worker.generators.phone_generator import generate_phone
    except ImportError:
        from generators.phone_generator import generate_phone


DEFAULT_STATIC_NAME = os.getenv("DEFAULT_STATIC_NAME", "Chaitanya Reddy")
DEFAULT_STATIC_PASSWORD = os.getenv("DEFAULT_STATIC_PASSWORD", "SecurePass@123")
DEFAULT_STATIC_PLACE = os.getenv("DEFAULT_STATIC_PLACE", "Hyderabad")
DEFAULT_STATIC_LANGUAGE = os.getenv("DEFAULT_STATIC_LANGUAGE", "en")


@dataclass(frozen=True)
class TestIdentity:
    __test__ = False
    account_id: str
    name: str = DEFAULT_STATIC_NAME
    test_id: str = ""
    phone: str = ""
    password: str = DEFAULT_STATIC_PASSWORD
    place: str = DEFAULT_STATIC_PLACE
    language: str = DEFAULT_STATIC_LANGUAGE
    referral: str = ""


def generate_identity(index: int, referral: str = "") -> TestIdentity:
    return TestIdentity(
        account_id=f"TEST{index:03d}",
        name=DEFAULT_STATIC_NAME,
        test_id=f"ident-{index:04d}",
        phone=generate_phone(index),
        password=DEFAULT_STATIC_PASSWORD,
        place=DEFAULT_STATIC_PLACE,
        language=DEFAULT_STATIC_LANGUAGE,
        referral=referral,
    )

