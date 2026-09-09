from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from queue import Empty, Queue
from typing import AsyncGenerator
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from worker.automation.signup_flow import run_mock_signup
from worker.generators.test_data import generate_identity
from worker.integrations.google_sheets import append_result
from backend.app.api.auth import Role, require_role
from backend.app.config import automation_mode, validate_automation_configuration
from worker.integrations.signup_adapter import AuthorizedPlaywrightAdapter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BatchStatus(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ErrorType(str, Enum):
    """Structured error types for better error tracking and debugging"""
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


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


class ReferralRequest(BaseModel):
    referral: str = Field(min_length=1, max_length=120)


class BatchResponse(BaseModel):
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
    started_at: str | None = None
    completed_at: str | None = None
    estimated_remaining: int = 0
    status: BatchStatus
    created_at: str


DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "signup_automation.db"
TARGET_SIZE = 1000
MAX_SIGNUP_RETRIES = int(os.getenv("MAX_SIGNUP_RETRIES", "3"))
RETRY_DELAY_SECONDS = float(os.getenv("RETRY_DELAY_SECONDS", "2"))
RETRY_BACKOFF_MULTIPLIER = float(os.getenv("RETRY_BACKOFF_MULTIPLIER", "2"))
WORKER_ID = os.getenv("WORKER_ID", f"worker-{uuid4().hex[:8]}")
WORKER_LEASE_SECONDS = float(os.getenv("WORKER_LEASE_SECONDS", "30"))


def run_signup(identity):
    """Run the configured adapter, keeping live automation opt-in and bounded."""
    if automation_mode() == "mock":
        return run_mock_signup(identity)
    return AuthorizedPlaywrightAdapter().signup(identity)
job_queue: Queue[str] = Queue()
subscribers: dict[str, list[Queue[dict]]] = {}
state_lock = threading.Lock()
pause_events: dict[str, threading.Event] = {}
stop_events: dict[str, threading.Event] = {}
rate_limit_lock = threading.Lock()
request_windows: dict[str, list[float]] = {}
known_account_ids: set[str] = set()
known_test_numbers: set[str] = set()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    logger.info("Initializing database...")
    with closing(connect()) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS batches ("
            "id TEXT PRIMARY KEY, referral TEXT NOT NULL, target INTEGER NOT NULL, "
            "successful INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0, "
            "status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS jobs ("
            "id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, status TEXT NOT NULL, "
            "worker_id TEXT, started_at TEXT, heartbeat_at TEXT, acknowledged_at TEXT)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS authorized_test_identities ("
            "id TEXT PRIMARY KEY, identifier TEXT NOT NULL UNIQUE, status TEXT NOT NULL, "
            "created_at TEXT NOT NULL, used_at TEXT, batch_id TEXT)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, "
            "status TEXT NOT NULL, error TEXT, attempt_number INTEGER NOT NULL, created_at TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS accounts ("
            "id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, phone TEXT NOT NULL, password TEXT NOT NULL, "
            "name TEXT, place TEXT, referral TEXT, language TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        # Backfill accounts from results_export.jsonl if present
        export_file = RESULTS_PATH if 'RESULTS_PATH' in globals() else (DATABASE_PATH.parent / "results_export.jsonl")
        if export_file.exists():
            try:
                with export_file.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            data = json.loads(line)
                            if data.get("phone") and data.get("batch_id"):
                                connection.execute(
                                    "INSERT OR IGNORE INTO accounts (id, batch_id, phone, password, name, place, referral, language, status, created_at) "
                                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                    (
                                        data.get("id") or str(uuid4()),
                                        data["batch_id"],
                                        data["phone"],
                                        data.get("password", ""),
                                        data.get("name", ""),
                                        data.get("place", ""),
                                        data.get("referral", ""),
                                        data.get("language", ""),
                                        data.get("status", "SUCCESS"),
                                        data.get("created_at", now()),
                                    )
                                )
            except Exception as e:
                logger.warning(f"Accounts backfill skipped: {e}")
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(batches)")}
        for name, definition in (
            ("skipped", "INTEGER NOT NULL DEFAULT 0"),
            ("attempted", "INTEGER NOT NULL DEFAULT 0"),
            ("retries", "INTEGER NOT NULL DEFAULT 0"),
            ("started_at", "TEXT"),
            ("completed_at", "TEXT"),
        ):
            if name not in columns:
                try:
                    logger.info(f"Adding column to batches: {name}")
                    connection.execute(f"ALTER TABLE batches ADD COLUMN {name} {definition}")
                except sqlite3.OperationalError:
                    pass
        connection.commit()
    logger.info("Database initialization complete")


def get_batch(batch_id: str) -> dict:
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT id, referral, target, successful, failed, skipped, attempted, retries, status, "
            "created_at, started_at, completed_at FROM batches WHERE id = ?",
            (batch_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    batch = dict(row)
    progress = calculate_batch_progress(batch)
    batch.update(progress)
    return batch


def calculate_batch_progress(batch: str | dict) -> dict:
    if isinstance(batch, str):
        batch = get_batch(batch)

    target = max(int(batch.get("target", 0) or 0), 0)
    successful = max(int(batch.get("successful", 0) or 0), 0)
    failed = max(int(batch.get("failed", 0) or 0), 0)
    skipped = max(int(batch.get("skipped", 0) or 0), 0)
    attempted = max(int(batch.get("attempted", 0) or 0), 0)
    retries = max(int(batch.get("retries", 0) or 0), 0)

    if attempted == 0:
        attempted = successful + failed + skipped

    remaining = max(target - successful, 0)
    if target <= 0:
        progress_percent = 0
    else:
        progress_percent = min(100, max(0, round((successful / target) * 100)))

    return {
        "target": target,
        "successful": successful,
        "failed": failed,
        "skipped": skipped,
        "attempted": attempted,
        "retries": retries,
        "remaining": remaining,
        "progress_percent": progress_percent,
        "estimated_remaining": remaining,
        "started_at": batch.get("started_at"),
        "completed_at": batch.get("completed_at"),
    }


def publish(batch_id: str, batch: dict) -> None:
    with state_lock:
        queues = list(subscribers.get(batch_id, []))
    for subscriber in queues:
        try:
            subscriber.put_nowait(batch)
        except Exception:
            continue


def publish_retry(batch_id: str, retry: int, error: str = "") -> None:
    batch = get_batch(batch_id)
    batch["event"] = "retry"
    batch["retry"] = retry
    if error:
        batch["error"] = error
    publish(batch_id, batch)


def calculate_retry_delay(attempt: int) -> float:
    if attempt <= 0:
        return 0.0
    return RETRY_DELAY_SECONDS * (RETRY_BACKOFF_MULTIPLIER ** (attempt - 1))


def should_retry(status: str, batch_status: str | None, retry_count: int) -> bool:
    if not status:
        return False
    if batch_status in {BatchStatus.CANCELLED.value, BatchStatus.COMPLETED.value, BatchStatus.FAILED.value}:
        return False
    if status == "DUPLICATE":
        return False
    if retry_count >= MAX_SIGNUP_RETRIES:
        return False
    return status in {"FAILURE", "ERROR", "TIMEOUT"}


def update_batch(batch_id: str, **changes: object) -> dict:
    changes["updated_at"] = now()
    assignments = ", ".join(f"{key} = ?" for key in changes)
    values = [*changes.values(), batch_id]
    with closing(connect()) as connection:
        connection.execute(f"UPDATE batches SET {assignments} WHERE id = ?", values)
        connection.commit()
    batch = get_batch(batch_id)
    publish(batch_id, batch)
    return batch


def create_job(batch_id: str) -> str:
    job_id = str(uuid4())
    with closing(connect()) as connection:
        connection.execute(
            "INSERT INTO jobs (id, batch_id, status) VALUES (?, ?, ?)",
            (job_id, batch_id, "QUEUED"),
        )
        connection.commit()
    return job_id


def claim_job(batch_id: str) -> str | None:
    with closing(connect()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id FROM jobs WHERE batch_id = ? AND status = 'QUEUED' ORDER BY rowid LIMIT 1",
            (batch_id,),
        ).fetchone()
        if row is None:
            batch = connection.execute(
                "SELECT status FROM batches WHERE id = ?",
                (batch_id,),
            ).fetchone()
            if batch is None or batch["status"] != BatchStatus.QUEUED.value:
                connection.rollback()
                return None
            job_id = str(uuid4())
            connection.execute(
                "INSERT INTO jobs (id, batch_id, status) VALUES (?, ?, 'RUNNING')",
                (job_id, batch_id),
            )
            timestamp = now()
            connection.execute(
                "UPDATE jobs SET worker_id = ?, started_at = ?, heartbeat_at = ? WHERE id = ?",
                (WORKER_ID, timestamp, timestamp, job_id),
            )
            connection.commit()
            return job_id
        job_id = row["id"]
        timestamp = now()
        connection.execute(
            "UPDATE jobs SET status = 'RUNNING', worker_id = ?, started_at = ?, heartbeat_at = ? WHERE id = ? AND status = 'QUEUED'",
            (WORKER_ID, timestamp, timestamp, job_id),
        )
        connection.commit()
    return job_id


def heartbeat_job(job_id: str) -> None:
    with closing(connect()) as connection:
        connection.execute(
            "UPDATE jobs SET heartbeat_at = ? WHERE id = ? AND worker_id = ? AND status = 'RUNNING'",
            (now(), job_id, WORKER_ID),
        )
        connection.commit()


def acknowledge_job(job_id: str, status: str = "COMPLETED") -> None:
    with closing(connect()) as connection:
        connection.execute(
            "UPDATE jobs SET status = ?, acknowledged_at = ? WHERE id = ? AND worker_id = ?",
            (status, now(), job_id, WORKER_ID),
        )
        connection.commit()


def recover_abandoned_jobs() -> int:
    cutoff = datetime.now(timezone.utc).timestamp() - WORKER_LEASE_SECONDS
    recovered = 0
    try:
        with closing(connect()) as connection:
            rows = connection.execute(
                "SELECT id, batch_id, heartbeat_at FROM jobs WHERE status = 'RUNNING'"
            ).fetchall()
            for row in rows:
                heartbeat = row["heartbeat_at"]
                if not heartbeat or datetime.fromisoformat(heartbeat).timestamp() < cutoff:
                    connection.execute(
                        "UPDATE jobs SET status = 'QUEUED', worker_id = NULL, started_at = NULL, heartbeat_at = NULL WHERE id = ?",
                        (row["id"],),
                    )
                    job_queue.put(row["batch_id"])
                    recovered += 1
            connection.commit()
    except sqlite3.OperationalError:
        initialize_database()
    return recovered


def record_success(batch_id: str, account_id: str, test_id: str) -> dict | None:
    with closing(connect()) as connection:
        cursor = connection.execute(
            "UPDATE batches SET successful = successful + 1, attempted = attempted + 1, updated_at = ? "
            "WHERE id = ? AND status = ? AND successful < target",
            (now(), batch_id, BatchStatus.RUNNING.value),
        )
        connection.commit()
    if cursor.rowcount != 1:
        return None
    known_account_ids.add(account_id)
    known_test_numbers.add(test_id)
    finalize_identity(test_id, "COMPLETED", batch_id)
    batch = get_batch(batch_id)
    publish(batch_id, batch)
    return batch


def claim_next_available_identity(batch_id: str) -> str | None:
    """Atomically find and reserve an AVAILABLE identity for this batch."""
    with closing(connect()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT identifier FROM authorized_test_identities WHERE status = 'AVAILABLE' ORDER BY rowid LIMIT 1"
        ).fetchone()
        if row is None:
            connection.rollback()
            return None
        identifier = row["identifier"]
        connection.execute(
            "UPDATE authorized_test_identities SET status = 'RESERVED', batch_id = ? WHERE identifier = ? AND status = 'AVAILABLE'",
            (batch_id, identifier),
        )
        connection.commit()
        return identifier


def reserve_identity(identifier: str, batch_id: str) -> bool:
    """Atomically reserve one identity; a second worker cannot reuse it."""
    with closing(connect()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT status FROM authorized_test_identities WHERE identifier = ?",
            (identifier,),
        ).fetchone()
        if existing:
            if existing["status"] == "AVAILABLE":
                connection.execute(
                    "UPDATE authorized_test_identities SET status = 'RESERVED', batch_id = ? WHERE identifier = ?",
                    (batch_id, identifier),
                )
                connection.commit()
                return True
            connection.rollback()
            return False
        try:
            connection.execute(
                "INSERT INTO authorized_test_identities (id, identifier, status, created_at, batch_id) VALUES (?, ?, 'RESERVED', ?, ?)",
                (str(uuid4()), identifier, now(), batch_id),
            )
            connection.commit()
            return True
        except sqlite3.IntegrityError:
            connection.rollback()
            return False


def mark_identity_processing(identifier: str, batch_id: str) -> None:
    """Move identity state from RESERVED to PROCESSING."""
    with closing(connect()) as connection:
        connection.execute(
            "UPDATE authorized_test_identities SET status = 'PROCESSING' WHERE identifier = ? AND batch_id = ?",
            (identifier, batch_id),
        )
        connection.commit()


def finalize_identity(identifier: str, status: str, batch_id: str) -> None:
    """Finalize identity with SUCCESS, FAILED, or SKIPPED."""
    with closing(connect()) as connection:
        connection.execute(
            "UPDATE authorized_test_identities SET status = ?, used_at = ?, batch_id = ? WHERE identifier = ?",
            (status, now(), batch_id, identifier),
        )
        connection.commit()


def seed_authorized_identities(identifiers: list[str]) -> int:
    """Seed test identities into the database with AVAILABLE status."""
    inserted = 0
    with closing(connect()) as connection:
        for ident in identifiers:
            ident = ident.strip()
            if not ident:
                continue
            try:
                connection.execute(
                    "INSERT INTO authorized_test_identities (id, identifier, status, created_at) VALUES (?, ?, 'AVAILABLE', ?)",
                    (str(uuid4()), ident, now()),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                pass
        connection.commit()
    return inserted


def cleanup_worker_events(batch_id: str) -> None:
    pause_events.pop(batch_id, None)
    stop_events.pop(batch_id, None)


def transition_batch(batch_id: str, target_status: str, detail: str) -> dict:
    with closing(connect()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT status FROM batches WHERE id = ?",
            (batch_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Batch not found")
        current_status = row["status"]
        if target_status not in ALLOWED_STATE_TRANSITIONS.get(current_status, set()):
            raise HTTPException(status_code=409, detail=detail)
        connection.execute(
            "UPDATE batches SET status = ?, updated_at = ? WHERE id = ? AND status = ?",
            (target_status, now(), batch_id, current_status),
        )
        connection.commit()
    batch = get_batch(batch_id)
    publish(batch_id, batch)
    return batch


def claim_queued_batch(batch_id: str) -> bool:
    """Atomically claim a queued batch for one worker."""
    timestamp = now()
    with closing(connect()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """
            UPDATE batches
            SET status = ?, updated_at = ?, started_at = COALESCE(started_at, ?)
            WHERE id = ? AND status = ?
            """,
            (
                BatchStatus.RUNNING.value,
                timestamp,
                timestamp,
                batch_id,
                BatchStatus.QUEUED.value,
            ),
        )
        connection.commit()

    if cursor.rowcount != 1:
        return False

    publish(batch_id, get_batch(batch_id))
    return True


def create_batch(referral: str) -> dict:
    batch_id = str(uuid4())
    timestamp = now()
    logger.info(f"Creating batch {batch_id} for referral: {referral}")
    with closing(connect()) as connection:
        connection.execute(
            "INSERT INTO batches (id, referral, target, status, created_at, updated_at, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (batch_id, referral.strip(), TARGET_SIZE, BatchStatus.CREATED.value, timestamp, timestamp, None),
        )
        connection.commit()
    logger.info(f"Batch {batch_id} created successfully")
    return get_batch(batch_id)


def process_batch(batch_id: str) -> None:
    logger.info(f"Starting to process batch {batch_id}")
    pause_event = pause_events.setdefault(batch_id, threading.Event())
    stop_event = stop_events.setdefault(batch_id, threading.Event())

    job_id = claim_job(batch_id)
    if job_id is None:
        logger.warning(f"Failed to claim job for batch {batch_id}")
        return

    try:
        if not claim_queued_batch(batch_id):
            logger.info(f"Batch {batch_id} already running or not queued, skipping")
            acknowledge_job(job_id, "SKIPPED")
            return

        attempt = 0
        while True:
            batch = get_batch(batch_id)
            if batch["successful"] >= batch["target"]:
                logger.info(f"Batch {batch_id} completed with {batch['successful']} successful signups")
                update_batch(batch_id, completed_at=now(), status=BatchStatus.COMPLETED.value)
                acknowledge_job(job_id)
                return
            if stop_event.is_set() or batch["status"] == BatchStatus.STOPPING.value:
                logger.info(f"Batch {batch_id} is being stopped")
                if batch["status"] == BatchStatus.PAUSED.value:
                    transition_batch(batch_id, BatchStatus.STOPPING.value, "Only paused batches can stop")
                transition_batch(batch_id, BatchStatus.CANCELLED.value, "Only stopping batches can cancel")
                acknowledge_job(job_id, "CANCELLED")
                return
            if batch["status"] == BatchStatus.PAUSED.value:
                pause_event.wait(0.05)
                continue
            if batch["status"] != BatchStatus.RUNNING.value:
                acknowledge_job(job_id, "STOPPED")
                return

            available_ident = claim_next_available_identity(batch_id)
            if available_ident:
                identity = TestIdentity(
                    account_id=available_ident,
                    test_id=available_ident,
                    phone=available_ident,
                    referral=batch.get("referral", ""),
                )
            else:
                try:
                    identity = generate_identity(attempt, referral=batch.get("referral", ""))
                except TypeError:
                    identity = generate_identity(attempt)
                attempt += 1
                if identity.account_id in known_account_ids or identity.test_id in known_test_numbers:
                    continue
                if not reserve_identity(identity.test_id, batch_id):
                    continue

            current = get_batch(batch_id)
            if current["status"] != BatchStatus.RUNNING.value or stop_event.is_set():
                continue

            mark_identity_processing(identity.test_id, batch_id)

            for retry in range(MAX_SIGNUP_RETRIES + 1):
                heartbeat_job(job_id)
                current = get_batch(batch_id)
                if stop_event.is_set() or current["status"] == BatchStatus.STOPPING.value:
                    transition_batch(batch_id, BatchStatus.CANCELLED.value, "Only stopping batches can cancel")
                    acknowledge_job(job_id, "CANCELLED")
                    return
                if current["status"] != BatchStatus.RUNNING.value:
                    return
                result = run_signup(identity)
                with closing(connect()) as connection:
                    connection.execute(
                        "INSERT INTO attempts (id, job_id, status, error, attempt_number, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (str(uuid4()), job_id, result.status, getattr(result, "error", ""), retry + 1, now()),
                    )
                    connection.commit()
                if result.status == "SUCCESS":
                    logger.info(f"Batch {batch_id}: Signup successful for {identity.account_id}")
                    recorded_batch = record_success(batch_id, result.account_id, identity.test_id)
                    if recorded_batch is not None:
                        try:
                            with closing(connect()) as conn_acc:
                                conn_acc.execute(
                                    "INSERT OR REPLACE INTO accounts (id, batch_id, phone, password, name, place, referral, language, status, created_at) "
                                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                    (
                                        result.account_id,
                                        batch_id,
                                        identity.phone,
                                        getattr(identity, "password", ""),
                                        identity.name,
                                        getattr(identity, "place", ""),
                                        recorded_batch["referral"],
                                        getattr(identity, "language", ""),
                                        result.status,
                                        getattr(result, "timestamp", now()),
                                    ),
                                )
                                conn_acc.commit()
                        except Exception as err:
                            logger.warning(f"Could not record account into accounts table: {err}")
                        append_result({
                            "id": result.account_id,
                            "name": identity.name,
                            "test_id": identity.test_id,
                            "phone": identity.phone,
                            "password": getattr(identity, "password", ""),
                            "place": getattr(identity, "place", ""),
                            "language": getattr(identity, "language", ""),
                            "referral": recorded_batch["referral"],
                            "batch_id": batch_id,
                            "status": result.status,
                            "error": getattr(result, "error", ""),
                            "created_at": getattr(result, "timestamp", now()),
                        })
                    break
                if result.status == "DUPLICATE":
                    logger.info(f"Batch {batch_id}: Duplicate identity {identity.account_id} - skipped")
                    current = get_batch(batch_id)
                    recorded_batch = update_batch(batch_id, skipped=current["skipped"] + 1, attempted=current["attempted"] + 1)
                    finalize_identity(identity.test_id, "SKIPPED", batch_id)
                    append_result({
                        "id": result.account_id,
                        "name": identity.name,
                        "test_id": identity.test_id,
                        "phone": identity.phone,
                        "password": getattr(identity, "password", ""),
                        "place": getattr(identity, "place", ""),
                        "language": getattr(identity, "language", ""),
                        "referral": recorded_batch["referral"],
                        "batch_id": batch_id,
                        "status": "SKIPPED",
                        "error": getattr(result, "error", "Duplicate account skipped"),
                        "created_at": getattr(result, "timestamp", now()),
                    })
                    break
                if should_retry(result.status, current["status"], retry):
                    next_retry = retry + 1
                    logger.warning(f"Batch {batch_id}: Retry {next_retry} for {identity.account_id} (status: {result.status})")
                    current = get_batch(batch_id)
                    update_batch(batch_id, retries=current["retries"] + 1, attempted=current["attempted"] + 1)
                    publish_retry(batch_id, next_retry, getattr(result, "error", ""))
                    delay = calculate_retry_delay(next_retry)
                    if delay > 0:
                        time.sleep(delay)
                    continue
                current = get_batch(batch_id)
                logger.warning(f"Batch {batch_id}: Signup failed for {identity.account_id}")
                update_batch(batch_id, failed=current["failed"] + 1, attempted=current["attempted"] + 1)
                finalize_identity(identity.test_id, "FAILED", batch_id)
                break
            time.sleep(0.01)
    except Exception as e:
        logger.error(f"Error processing batch {batch_id}: {e}", exc_info=True)
        try:
            batch = get_batch(batch_id)
            if batch["status"] not in (BatchStatus.CANCELLED.value, BatchStatus.COMPLETED.value):
                update_batch(batch_id, status=BatchStatus.FAILED.value)
        finally:
            acknowledge_job(job_id, "FAILED")
            raise
    finally:
        cleanup_worker_events(batch_id)


def worker_loop() -> None:
    logger.info("Worker loop started")
    while True:
        recovered = recover_abandoned_jobs()
        if recovered > 0:
            logger.info(f"Recovered {recovered} abandoned jobs")
        try:
            batch_id = job_queue.get(timeout=0.2)
        except Empty:
            continue
        try:
            process_batch(batch_id)
        except Exception as e:
            logger.error(f"Error in worker loop for batch {batch_id}: {e}", exc_info=True)
            cleanup_worker_events(batch_id)
        finally:
            job_queue.task_done()


app = FastAPI(title="Signup Automation API", version="1.0.0")

# Configure CORS from environment
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:5173")
allowed_origins = [
    frontend_origin,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# Add additional origins from environment variable if provided
additional_origins = os.getenv("ADDITIONAL_CORS_ORIGINS", "").split(",")
allowed_origins.extend([o.strip() for o in additional_origins if o.strip()])

logger.info(f"CORS allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """Bound local rate limiting; Redis should replace this for multi-instance use."""
    if request.url.path in {"/health", "/healthz", "/ready"}:
        return await call_next(request)
    limit = int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "100"))
    client = request.client.host if request.client else "unknown"
    cutoff = time.monotonic() - 60
    with rate_limit_lock:
        window = [stamp for stamp in request_windows.get(client, []) if stamp >= cutoff]
        if len(window) >= limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        window.append(time.monotonic())
        request_windows[client] = window
    return await call_next(request)


@app.on_event("startup")
def startup() -> None:
    logger.info("Starting up Signup Automation API...")
    validate_automation_configuration()
    logger.info(f"Worker ID: {WORKER_ID}")
    logger.info(f"Database path: {DATABASE_PATH}")
    initialize_database()
    if os.getenv("EMBEDDED_WORKER", "true").lower() != "true":
        logger.info("Embedded worker disabled; expecting a separate worker service")
        return
    worker_thread = threading.Thread(target=worker_loop, daemon=True, name="mock-worker")
    worker_thread.start()
    logger.info("Startup complete")


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Signup Automation API is running"}


@app.get("/health")
@app.get("/healthz")
def health() -> dict[str, str]:
    try:
        with closing(connect()) as connection:
            connection.execute("SELECT 1").fetchone()
        logger.info("Health check: healthy")
        return {"status": "healthy", "database": "connected"}
    except sqlite3.Error as e:
        logger.error(f"Health check failed: database disconnected - {e}")
        return {"status": "degraded", "database": "disconnected"}


@app.get("/ready")
def readiness() -> dict[str, str]:
    """Readiness check - verifies system is ready to receive traffic"""
    try:
        # Check database connection
        with closing(connect()) as connection:
            connection.execute("SELECT 1").fetchone()
        
        # Check worker thread is running (would need to add a flag for this)
        worker_status = "running" if threading.active_count() > 1 else "starting"
        
        logger.info("Readiness check: ready")
        return {
            "status": "ready",
            "database": "ok",
            "worker": worker_status
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {
            "status": "not_ready",
            "database": "error",
            "worker": "error"
        }


@app.post("/referrals", dependencies=[Depends(require_role(Role.ADMIN, Role.OPERATOR))])
def create_referral(data: ReferralRequest) -> dict[str, object]:
    batch = create_batch(data.referral)
    return {"message": "Referral received", **batch}


class SeedIdentitiesRequest(BaseModel):
    identifiers: list[str] = Field(min_length=1)


@app.post("/identities/seed", dependencies=[Depends(require_role(Role.ADMIN, Role.OPERATOR))])
def seed_identities(data: SeedIdentitiesRequest) -> dict[str, object]:
    count = seed_authorized_identities(data.identifiers)
    return {"seeded": count, "total_requested": len(data.identifiers)}


@app.post("/batches", response_model=BatchResponse, dependencies=[Depends(require_role(Role.ADMIN, Role.OPERATOR))])
def post_batch(data: ReferralRequest) -> dict:
    return create_batch(data.referral)


@app.get("/batches/{batch_id}", response_model=BatchResponse, dependencies=[Depends(require_role(Role.ADMIN, Role.OPERATOR, Role.VIEWER))])
def read_batch(batch_id: str) -> dict:
    return get_batch(batch_id)


@app.post("/batches/{batch_id}/start", response_model=BatchResponse, dependencies=[Depends(require_role(Role.ADMIN, Role.OPERATOR))])
def start_batch(batch_id: str) -> dict:
    logger.info(f"Starting batch {batch_id}")
    transition_batch(batch_id, BatchStatus.QUEUED.value, "Only CREATED batches can be started")
    update_batch(batch_id, started_at=now())
    pause_events.setdefault(batch_id, threading.Event()).clear()
    stop_events.setdefault(batch_id, threading.Event()).clear()
    create_job(batch_id)
    job_queue.put(batch_id)
    logger.info(f"Batch {batch_id} started successfully")
    return get_batch(batch_id)


@app.post("/batches/{batch_id}/pause", response_model=BatchResponse, dependencies=[Depends(require_role(Role.ADMIN, Role.OPERATOR))])
def pause_batch(batch_id: str) -> dict:
    logger.info(f"Pausing batch {batch_id}")
    batch = transition_batch(batch_id, BatchStatus.PAUSED.value, "Only running batches can be paused")
    pause_events.setdefault(batch_id, threading.Event()).set()
    return batch


@app.post("/batches/{batch_id}/resume", response_model=BatchResponse, dependencies=[Depends(require_role(Role.ADMIN, Role.OPERATOR))])
def resume_batch(batch_id: str) -> dict:
    logger.info(f"Resuming batch {batch_id}")
    batch = transition_batch(batch_id, BatchStatus.RUNNING.value, "Only paused batches can be resumed")
    pause_events.setdefault(batch_id, threading.Event()).clear()
    return batch


@app.post("/batches/{batch_id}/stop", response_model=BatchResponse, dependencies=[Depends(require_role(Role.ADMIN, Role.OPERATOR))])
def stop_batch(batch_id: str) -> dict:
    logger.info(f"Stopping batch {batch_id}")
    batch = transition_batch(
        batch_id,
        BatchStatus.STOPPING.value,
        "Only running or paused batches can be stopped",
    )
    stop_events.setdefault(batch_id, threading.Event()).set()
    return batch


@app.get("/batches/{batch_id}/events", dependencies=[Depends(require_role(Role.ADMIN, Role.OPERATOR, Role.VIEWER))])
async def batch_events(batch_id: str) -> StreamingResponse:
    get_batch(batch_id)
    updates: Queue[dict] = Queue()
    with state_lock:
        subscribers.setdefault(batch_id, []).append(updates)

    async def stream() -> AsyncGenerator[str, None]:
        try:
            updates.put(get_batch(batch_id))
            while True:
                try:
                    batch = await asyncio.to_thread(updates.get, True, 0.5)
                    yield f"data: {json.dumps(batch)}\n\n"
                    if batch["status"] in (BatchStatus.COMPLETED.value, BatchStatus.CANCELLED.value, BatchStatus.FAILED.value):
                        return
                except Empty:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0)
        finally:
            with state_lock:
                queue_list = subscribers.get(batch_id)
async def batch_events(batch_id: str) -> StreamingResponse:
    get_batch(batch_id)
    updates: Queue[dict] = Queue()
    with state_lock:
        subscribers.setdefault(batch_id, []).append(updates)

    async def stream() -> AsyncGenerator[str, None]:
        try:
            updates.put(get_batch(batch_id))
            while True:
                try:
                    batch = await asyncio.to_thread(updates.get, True, 0.5)
                    yield f"data: {json.dumps(batch)}\n\n"
                    if batch["status"] in (BatchStatus.COMPLETED.value, BatchStatus.CANCELLED.value, BatchStatus.FAILED.value):
                        return
                except Empty:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0)
        finally:
            with state_lock:
                queue_list = subscribers.get(batch_id)
                if queue_list and updates in queue_list:
                    queue_list.remove(updates)
                if queue_list == []:
                    subscribers.pop(batch_id, None)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/batches/{batch_id}/accounts")
def get_batch_accounts(batch_id: str, limit: int = 200):
    with closing(connect()) as connection:
        rows = connection.execute(
            "SELECT id, batch_id, phone, password, name, place, referral, language, status, created_at "
            "FROM accounts WHERE batch_id = ? ORDER BY created_at DESC LIMIT ?",
            (batch_id, limit),
        ).fetchall()
        return {"accounts": [dict(r) for r in rows]}


@app.get("/batches/{batch_id}/export/csv", dependencies=[Depends(require_role(Role.ADMIN, Role.OPERATOR, Role.VIEWER))])
def export_batch_csv(batch_id: str):
    batch = get_batch(batch_id)
    with closing(connect()) as connection:
        accounts = connection.execute(
            "SELECT phone, password, place, referral, name, language, status, created_at, id FROM accounts WHERE batch_id = ? ORDER BY created_at ASC",
            (batch_id,)
        ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Phone Number", "Password", "Place", "Referral Code", "Name", "Language", "Status", "Timestamp", "Account ID", "Batch ID"])
    if accounts:
        for acc in accounts:
            writer.writerow([
                acc["phone"],
                acc["password"],
                acc["place"] or "",
                acc["referral"] or batch.get("referral", ""),
                acc["name"] or "",
                acc["language"] or "",
                acc["status"],
                acc["created_at"],
                acc["id"],
                batch_id,
            ])
    else:
        writer.writerow(["N/A", "N/A", "N/A", batch.get("referral", "N/A"), "N/A", "N/A", batch.get("status", "N/A"), batch.get("created_at", ""), "N/A", batch_id])

    output.seek(0)
    filename = f"batch_{batch_id[:8]}_accounts.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.get("/batches/{batch_id}/export/json", dependencies=[Depends(require_role(Role.ADMIN, Role.OPERATOR, Role.VIEWER))])
def export_batch_json(batch_id: str):
    batch = get_batch(batch_id)
    with closing(connect()) as connection:
        accounts = [dict(row) for row in connection.execute(
            "SELECT id, phone, password, name, place, referral, language, status, created_at FROM accounts WHERE batch_id = ? ORDER BY created_at ASC",
            (batch_id,)
        ).fetchall()]

    data = {
        "batch": batch,
        "accounts": accounts,
        "exported_at": now(),
    }
    filename = f"batch_{batch_id[:8]}_accounts.json"
    return StreamingResponse(
        iter([json.dumps(data, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.get("/workers", dependencies=[Depends(require_role(Role.ADMIN, Role.OPERATOR, Role.VIEWER))])
def list_workers():
    with closing(connect()) as connection:
        jobs = [dict(row) for row in connection.execute(
            "SELECT id, batch_id, status, worker_id, started_at, heartbeat_at FROM jobs ORDER BY rowid DESC LIMIT 50"
        ).fetchall()]
    return {
        "active_worker_id": WORKER_ID,
        "queue_size": job_queue.qsize(),
        "recent_jobs": jobs,
        "timestamp": now()
    }
