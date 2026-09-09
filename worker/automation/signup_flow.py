from dataclasses import dataclass, field
from datetime import datetime, timezone

try:
    from ..generators.test_data import TestIdentity
except ImportError:
    from generators.test_data import TestIdentity


@dataclass(frozen=True)
class SignupResult:
    account_id: str
    status: str
    error: str = ""
    phone: str = ""
    attempts: int = 1
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def success(cls, account_id: str, phone: str = "", attempts: int = 1) -> "SignupResult":
        return cls(account_id=account_id, status="SUCCESS", phone=phone, attempts=attempts)

    @classmethod
    def duplicate(cls, account_id: str, phone: str = "", attempts: int = 1) -> "SignupResult":
        return cls(account_id=account_id, status="DUPLICATE", phone=phone, attempts=attempts)

    @classmethod
    def failure(cls, account_id: str, error: str, phone: str = "", attempts: int = 1) -> "SignupResult":
        return cls(account_id=account_id, status="FAILURE", error=error, phone=phone, attempts=attempts)


def run_mock_signup(identity: TestIdentity) -> SignupResult:
    return SignupResult.success(identity.account_id)
