"""Batch management API endpoints."""

import logging
import re
from fastapi import APIRouter, HTTPException
from backend.app.models.models import BatchResponse, ReferralRequest, BulkReferralRequest, BatchStatus
from backend.app.main import (
    get_batch, create_batch, update_batch, transition_batch,
    create_job, job_queue,
    pause_events, stop_events,
    now
)

router = APIRouter(prefix="/batches", tags=["batches"])
logger = logging.getLogger(__name__)


@router.post("", response_model=BatchResponse)
def post_batch(data: ReferralRequest, auto_start: bool = False) -> dict:
    """Create a new batch, or multiple sequential queued batches if multiple codes are provided."""
    raw = data.referral.strip()
    codes = [c.strip() for c in re.split(r"[\r\n,;]+", raw) if c.strip()]
    if not codes:
        raise HTTPException(status_code=400, detail="Referral code cannot be empty")
    logger.info(f"Creating batch for primary referral: {codes[0]}")
    first_batch = create_batch(codes[0])
    should_start = auto_start or getattr(data, "auto_start", False)
    if should_start:
        first_batch = start_batch(first_batch["id"])
    for extra in codes[1:]:
        extra_b = create_batch(extra)
        if should_start:
            start_batch(extra_b["id"])
    return first_batch


@router.post("/bulk", response_model=list[BatchResponse])
def post_batches_bulk(data: BulkReferralRequest) -> list[dict]:
    """Create multiple sequential batches, queueing remaining tasks to run in order."""
    created = []
    for ref in data.referrals:
        cleaned = ref.strip()
        if cleaned:
            b = create_batch(cleaned)
            if data.auto_start:
                b = start_batch(b["id"])
            created.append(b)
    return created


@router.get("/{batch_id}", response_model=BatchResponse)
def read_batch(batch_id: str) -> dict:
    """Get batch details."""
    return get_batch(batch_id)


@router.post("/{batch_id}/start", response_model=BatchResponse)
def start_batch(batch_id: str) -> dict:
    """Start a batch."""
    logger.info(f"Starting batch {batch_id}")
    transition_batch(batch_id, BatchStatus.QUEUED.value, "Only CREATED batches can be started")
    update_batch(batch_id, started_at=now())
    pause_events.setdefault(batch_id, __import__('threading').Event()).clear()
    stop_events.setdefault(batch_id, __import__('threading').Event()).clear()
    create_job(batch_id)
    job_queue.put(batch_id)
    logger.info(f"Batch {batch_id} started successfully")
    return get_batch(batch_id)


@router.post("/{batch_id}/pause", response_model=BatchResponse)
def pause_batch(batch_id: str) -> dict:
    """Pause a batch."""
    logger.info(f"Pausing batch {batch_id}")
    batch = transition_batch(batch_id, BatchStatus.PAUSED.value, "Only running batches can be paused")
    pause_events.setdefault(batch_id, __import__('threading').Event()).set()
    return batch


@router.post("/{batch_id}/resume", response_model=BatchResponse)
def resume_batch(batch_id: str) -> dict:
    """Resume a batch."""
    logger.info(f"Resuming batch {batch_id}")
    batch = transition_batch(batch_id, BatchStatus.RUNNING.value, "Only paused batches can be resumed")
    pause_events.setdefault(batch_id, __import__('threading').Event()).clear()
    return batch


@router.post("/{batch_id}/stop", response_model=BatchResponse)
def stop_batch(batch_id: str) -> dict:
    """Stop a batch."""
    logger.info(f"Stopping batch {batch_id}")
    batch = transition_batch(
        batch_id,
        BatchStatus.STOPPING.value,
        "Only running or paused batches can be stopped",
    )
    stop_events.setdefault(batch_id, __import__('threading').Event()).set()
    return batch
