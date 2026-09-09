"""Data models for the application."""

from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional


class BatchStatus(str, Enum):
    """Batch processing status states."""
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ErrorType(str, Enum):
    """Structured error types for tracking."""
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    SITE_ERROR = "SITE_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class JobStatus(str, Enum):
    """Job status states."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABANDONED = "ABANDONED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


# ============================================================
# Request / Response Models
# ============================================================

class ReferralRequest(BaseModel):
    """Request model for creating a batch."""
    referral: str = Field(min_length=1, max_length=120)


class BatchResponse(BaseModel):
    """Response model for batch information."""
    id: str
    referral: str
    target: int
    successful: int
    failed: int
    skipped: int = 0
    attempted: int = 0
    retries: int = 0
    remaining: int = 0
    progress_percent: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    estimated_remaining: int = 0
    status: BatchStatus
    created_at: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    database: str


class ReadinessResponse(BaseModel):
    """Readiness check response."""
    status: str
    database: str
    worker: str


# ============================================================
# State Transitions
# ============================================================

ALLOWED_STATE_TRANSITIONS: dict[str, set[str]] = {
    BatchStatus.CREATED.value: {BatchStatus.QUEUED.value},
    BatchStatus.QUEUED.value: {BatchStatus.RUNNING.value},
    BatchStatus.RUNNING.value: {
        BatchStatus.PAUSED.value,
        BatchStatus.STOPPING.value,
        BatchStatus.COMPLETED.value,
    },
    BatchStatus.PAUSED.value: {
        BatchStatus.RUNNING.value,
        BatchStatus.STOPPING.value,
    },
    BatchStatus.STOPPING.value: {BatchStatus.CANCELLED.value},
}
