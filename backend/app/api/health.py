"""Health and status check endpoints."""

import logging
import sqlite3
import threading
from contextlib import closing
from fastapi import APIRouter
from backend.app.models.models import HealthResponse, ReadinessResponse
from backend.app.main import connect

router = APIRouter(prefix="", tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
def health() -> dict[str, str]:
    """Health check endpoint."""
    try:
        with closing(connect()) as connection:
            connection.execute("SELECT 1").fetchone()
        logger.info("Health check: healthy")
        return {"status": "healthy", "database": "connected"}
    except sqlite3.Error as e:
        logger.error(f"Health check failed: database disconnected - {e}")
        return {"status": "degraded", "database": "disconnected"}


@router.get("/ready", response_model=ReadinessResponse)
def readiness() -> dict[str, object]:
    """Readiness check - verifies system is ready to receive traffic."""
    try:
        from backend.app.main import job_queue
        with closing(connect()) as connection:
            connection.execute("SELECT 1").fetchone()
        
        active_workers = job_queue.get_active_workers(max_age_seconds=45.0)
        worker_status = "running" if (len(active_workers) > 0 or threading.active_count() > 1) else "starting"
        redis_status = "connected" if job_queue._redis is not None else "offline_or_local_fallback"
        
        logger.info("Readiness check: ready")
        return {
            "status": "ready",
            "database": "ok",
            "worker": worker_status,
            "redis": redis_status,
            "active_workers": len(active_workers),
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {
            "status": "not_ready",
            "database": "error",
            "worker": "error",
            "redis": "error",
            "active_workers": 0,
        }

