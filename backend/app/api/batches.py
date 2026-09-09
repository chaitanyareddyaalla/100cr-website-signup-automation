"""Batch management API endpoints."""

import logging
from fastapi import APIRouter, HTTPException
from backend.app.models.models import BatchResponse, ReferralRequest, BatchStatus
from backend.app.main import (
    get_batch, create_batch, update_batch, transition_batch,
    claim_job, create_job, acknowledge_job, job_queue,
    pause_events, stop_events
)

router = APIRouter(prefix="/batches", tags=["batches"])
logger = logging.getLogger(__name__)


@router.post("", response_model=BatchResponse)
def post_batch(data: ReferralRequest) -> dict:
    """Create a new batch."""
    logger.info(f"Creating batch for referral: {data.referral}")
    return create_batch(data.referral)


@router.get("/{batch_id}", response_model=BatchResponse)
def read_batch(batch_id: str) -> dict:
    """Get batch details."""
    return get_batch(batch_id)


@router.post("/{batch_id}/start", response_model=BatchResponse)
def start_batch(batch_id: str) -> dict:
    """Start a batch."""
    logger.info(f"Starting batch {batch_id}")
    transition_batch(batch_id, BatchStatus.QUEUED.value, "Only CREATED batches can be started")
    update_batch(batch_id, started_at=None)  # TODO: Use proper timestamp
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
