from dataclasses import dataclass


@dataclass(frozen=True)
class Batch:
    id: str
    referral: str
    target: int
    successful: int
    failed: int
    status: str
    created_at: str
