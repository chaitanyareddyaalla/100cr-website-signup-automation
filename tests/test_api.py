import asyncio
import json
import sqlite3
import threading
import time
from queue import Empty

import pytest
from fastapi.testclient import TestClient

import backend.app.main as backend_main
import worker.integrations.google_sheets as google_sheets
from backend.app.main import app, update_batch


@pytest.fixture(autouse=True)
def isolate_worker_state(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOMATION_MODE", "mock")
    monkeypatch.setenv("SIGNUP_CONCURRENCY", "1")
    monkeypatch.setenv("MAX_PARALLEL_SIGNUPS", "1")
    monkeypatch.setenv("MAX_CONSECUTIVE_FAILURES", "20")
    monkeypatch.setattr(backend_main, "DATABASE_PATH", tmp_path / "batches.db")
    monkeypatch.setattr(backend_main, "RETRY_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(backend_main, "_signup_in_flight", 0)
    backend_main.pause_events.clear()
    backend_main.stop_events.clear()
    backend_main.known_account_ids.clear()
    backend_main.known_test_numbers.clear()
    backend_main.global_used_phones.clear()
    while True:
        try:
            backend_main.job_queue.get_nowait()
            backend_main.job_queue.task_done()
        except Empty:
            break
    backend_main.initialize_database()
    yield
    backend_main.pause_events.clear()
    backend_main.stop_events.clear()


def queued_batch(target: int = 3) -> dict:
    batch = backend_main.create_batch("WORKER_TEST")
    update_batch(batch["id"], target=target)
    return backend_main.transition_batch(batch["id"], "QUEUED", "test")


def wait_for_status(batch_id: str, status: str) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if backend_main.get_batch(batch_id)["status"] == status:
            return
        time.sleep(0.005)
    raise AssertionError(f"batch did not reach {status}")


def test_health_reports_database() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "connected"


def test_recover_abandoned_jobs_handles_missing_table() -> None:
    db_path = backend_main.DATABASE_PATH
    backend_main.DATABASE_PATH = db_path.parent / "missing_jobs.db"
    try:
        assert backend_main.recover_abandoned_jobs() == 0
    finally:
        backend_main.DATABASE_PATH = db_path


def test_batch_lifecycle_controls() -> None:
    with TestClient(app) as client:
        batch = client.post("/batches", json={"referral": "TEST123"}).json()
        batch_id = batch["id"]
        assert batch["status"] == "CREATED"
        started = client.post(f"/batches/{batch_id}/start").json()
        assert started["status"] in ("QUEUED", "RUNNING")
        paused = client.post(f"/batches/{batch_id}/pause")
        assert paused.status_code in (200, 409)
        stopped = client.post(f"/batches/{batch_id}/stop")
        assert stopped.status_code == 200


@pytest.mark.parametrize(
    ("operation", "status"),
    [
        ("start", "COMPLETED"),
        ("start", "RUNNING"),
        ("start", "PAUSED"),
        ("pause", "CREATED"),
        ("pause", "COMPLETED"),
        ("resume", "CANCELLED"),
        ("stop", "CREATED"),
        ("stop", "COMPLETED"),
        ("stop", "CANCELLED"),
    ],
)
def test_invalid_batch_transition_returns_conflict(operation: str, status: str) -> None:
    with TestClient(app) as client:
        batch = client.post("/batches", json={"referral": "INVALID_TRANSITION"}).json()
        update_batch(batch["id"], status=status)

        response = client.post(f"/batches/{batch['id']}/{operation}")

    assert response.status_code == 409


def test_rapid_start_allows_only_one_queue_entry() -> None:
    batch = backend_main.create_batch("RAPID_START")
    update_batch(batch["id"], target=0)
    results = []

    def start() -> None:
        try:
            results.append(backend_main.start_batch(batch["id"])["status"])
        except Exception as error:
            results.append(error)

    first = threading.Thread(target=start)
    second = threading.Thread(target=start)
    first.start()
    second.start()
    first.join(2)
    second.join(2)

    assert results.count("QUEUED") == 1
    assert sum(isinstance(result, Exception) for result in results) == 1


def test_pause_after_completion_is_rejected() -> None:
    batch = backend_main.create_batch("PAUSE_COMPLETE")
    update_batch(batch["id"], status="COMPLETED")
    with pytest.raises(Exception):
        backend_main.pause_batch(batch["id"])


def test_resume_requires_paused_batch() -> None:
    batch = backend_main.create_batch("RESUME_RUNNING")
    update_batch(batch["id"], status="RUNNING")
    with pytest.raises(Exception):
        backend_main.resume_batch(batch["id"])


def test_stop_while_paused_can_cancel() -> None:
    batch = backend_main.create_batch("STOP_PAUSED")
    update_batch(batch["id"], status="PAUSED")
    backend_main.stop_batch(batch["id"])
    assert backend_main.get_batch(batch["id"])["status"] == "STOPPING"


def test_stop_after_cancellation_is_rejected() -> None:
    batch = backend_main.create_batch("STOP_CANCELLED")
    update_batch(batch["id"], status="CANCELLED")
    with pytest.raises(Exception):
        backend_main.stop_batch(batch["id"])


def test_concurrent_control_requests_leave_one_valid_state() -> None:
    batch = backend_main.create_batch("CONCURRENT_CONTROLS")
    update_batch(batch["id"], status="RUNNING")
    results = []

    def pause() -> None:
        try:
            results.append(backend_main.pause_batch(batch["id"])["status"])
        except Exception as error:
            results.append(error)

    first = threading.Thread(target=pause)
    second = threading.Thread(target=pause)
    first.start()
    second.start()
    first.join(2)
    second.join(2)

    assert results.count("PAUSED") == 1
    assert sum(isinstance(result, Exception) for result in results) == 1
    assert backend_main.get_batch(batch["id"])["status"] == "PAUSED"


def test_worker_moves_queued_to_running(monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()

    def signup(identity):
        started.set()
        release.wait(1)
        return type("Result", (), {"status": "SUCCESS", "account_id": identity.account_id})()

    monkeypatch.setattr(backend_main, "run_mock_signup", signup)
    batch = queued_batch()
    worker = threading.Thread(target=backend_main.process_batch, args=(batch["id"],))
    worker.start()
    assert started.wait(1)
    wait_for_status(batch["id"], "RUNNING")
    release.set()
    worker.join(2)


def test_worker_pauses(monkeypatch) -> None:
    monkeypatch.setattr(backend_main, "run_mock_signup", lambda identity: type("Result", (), {"status": "SUCCESS", "account_id": identity.account_id})())
    batch = queued_batch(20)
    worker = threading.Thread(target=backend_main.process_batch, args=(batch["id"],))
    worker.start()
    wait_for_status(batch["id"], "RUNNING")
    backend_main.pause_batch(batch["id"])
    time.sleep(0.05)
    paused_count = backend_main.get_batch(batch["id"])["successful"]
    time.sleep(0.05)
    assert backend_main.get_batch(batch["id"])["successful"] == paused_count
    backend_main.stop_batch(batch["id"])
    worker.join(2)


def test_worker_resumes(monkeypatch) -> None:
    monkeypatch.setattr(backend_main, "run_mock_signup", lambda identity: type("Result", (), {"status": "SUCCESS", "account_id": identity.account_id})())
    batch = queued_batch(20)
    worker = threading.Thread(target=backend_main.process_batch, args=(batch["id"],))
    worker.start()
    wait_for_status(batch["id"], "RUNNING")
    backend_main.pause_batch(batch["id"])
    paused_count = backend_main.get_batch(batch["id"])["successful"]
    backend_main.resume_batch(batch["id"])
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline and backend_main.get_batch(batch["id"])["successful"] <= paused_count:
        time.sleep(0.005)
    assert backend_main.get_batch(batch["id"])["successful"] > paused_count
    backend_main.stop_batch(batch["id"])
    worker.join(2)


def test_worker_stops(monkeypatch) -> None:
    monkeypatch.setattr(backend_main, "run_mock_signup", lambda identity: type("Result", (), {"status": "SUCCESS", "account_id": identity.account_id})())
    batch = queued_batch(100)
    worker = threading.Thread(target=backend_main.process_batch, args=(batch["id"],))
    worker.start()
    wait_for_status(batch["id"], "RUNNING")
    backend_main.stop_batch(batch["id"])
    worker.join(2)
    assert backend_main.get_batch(batch["id"])["status"] == "CANCELLED"


def test_worker_completes_at_target(monkeypatch) -> None:
    monkeypatch.setattr(backend_main, "run_mock_signup", lambda identity: type("Result", (), {"status": "SUCCESS", "account_id": identity.account_id})())
    batch = queued_batch(2)
    backend_main.process_batch(batch["id"])
    result = backend_main.get_batch(batch["id"])
    assert result["status"] == "COMPLETED"
    assert result["successful"] == 2


def test_worker_never_exceeds_target(monkeypatch) -> None:
    monkeypatch.setattr(backend_main, "run_mock_signup", lambda identity: type("Result", (), {"status": "SUCCESS", "account_id": identity.account_id})())
    batch = queued_batch(1)
    backend_main.process_batch(batch["id"])
    assert backend_main.get_batch(batch["id"])["successful"] == 1


def test_worker_handles_failure(monkeypatch) -> None:
    def fail(identity):
        raise RuntimeError("signup failed")

    monkeypatch.setattr(backend_main, "run_mock_signup", fail)
    batch = queued_batch()
    with pytest.raises(RuntimeError):
        backend_main.process_batch(batch["id"])
    assert backend_main.get_batch(batch["id"])["status"] == "FAILED"


def test_worker_retries_transient_failure(monkeypatch) -> None:
    results = iter(["FAILURE", "SUCCESS"])
    calls = []

    def signup(identity):
        calls.append(identity.account_id)
        status = next(results)
        return type("Result", (), {"status": status, "account_id": identity.account_id})()

    monkeypatch.setattr(backend_main, "run_mock_signup", signup)
    batch = queued_batch(1)
    backend_main.process_batch(batch["id"])
    result = backend_main.get_batch(batch["id"])
    assert result["status"] == "COMPLETED"
    assert result["successful"] == 1
    assert result["failed"] == 0
    assert len(calls) == 2


def test_worker_counts_failure_after_retries_and_continues(monkeypatch) -> None:
    phones = iter(["FAILED_PHONE", "SUCCESS_PHONE"])
    monkeypatch.setattr(backend_main, "claim_unique_phone", lambda batch_id: next(phones))
    monkeypatch.setattr(
        backend_main,
        "run_mock_signup",
        lambda identity: type("Result", (), {"status": "FAILURE" if identity.account_id == "FAILED_PHONE" else "SUCCESS", "account_id": identity.account_id})(),
    )
    batch = queued_batch(1)
    backend_main.process_batch(batch["id"])
    result = backend_main.get_batch(batch["id"])
    assert result["status"] == "COMPLETED"
    assert result["successful"] == 1
    assert result["failed"] == 1


def test_duplicate_result_is_not_retried_or_counted(monkeypatch) -> None:
    calls = []

    def signup(identity):
        calls.append(identity.account_id)
        status = "DUPLICATE" if identity.account_id == "DUPLICATE" else "SUCCESS"
        return type("Result", (), {"status": status, "account_id": identity.account_id})()

    phones = iter(["DUPLICATE", "UNIQUE"])
    monkeypatch.setattr(backend_main, "claim_unique_phone", lambda batch_id: next(phones))
    monkeypatch.setattr(backend_main, "run_mock_signup", signup)
    batch = queued_batch(1)
    backend_main.process_batch(batch["id"])
    result = backend_main.get_batch(batch["id"])
    assert result["status"] == "COMPLETED"
    assert result["successful"] == 1
    assert result["failed"] == 0
    assert calls == ["DUPLICATE", "UNIQUE"]


def test_worker_cleans_event_flags(monkeypatch) -> None:
    monkeypatch.setattr(backend_main, "run_mock_signup", lambda identity: type("Result", (), {"status": "SUCCESS", "account_id": identity.account_id})())
    batch = queued_batch(1)
    backend_main.process_batch(batch["id"])
    assert batch["id"] not in backend_main.pause_events
    assert batch["id"] not in backend_main.stop_events


def test_duplicate_number_is_skipped(monkeypatch) -> None:
    phones = iter(["DUPLICATE", "UNIQUE"])
    monkeypatch.setattr(backend_main, "claim_unique_phone", lambda batch_id: next(phones))

    def signup(identity):
        status = "DUPLICATE" if identity.account_id == "DUPLICATE" else "SUCCESS"
        return type("Result", (), {"status": status, "account_id": identity.account_id, "error": "", "timestamp": ""})()

    monkeypatch.setattr(backend_main, "run_mock_signup", signup)
    batch = queued_batch(1)
    backend_main.process_batch(batch["id"])
    assert backend_main.get_batch(batch["id"])["successful"] == 1
    assert backend_main.get_batch(batch["id"])["skipped"] == 1


def test_duplicate_does_not_count_as_success(monkeypatch) -> None:
    phones = iter(["duplicate", "unique"])
    monkeypatch.setattr(backend_main, "claim_unique_phone", lambda batch_id: next(phones))

    def signup(identity):
        status = "DUPLICATE" if identity.account_id == "duplicate" else "SUCCESS"
        return type("Result", (), {"status": status, "account_id": identity.account_id, "error": "", "timestamp": ""})()

    monkeypatch.setattr(backend_main, "run_mock_signup", signup)
    batch = queued_batch(1)
    backend_main.process_batch(batch["id"])
    result = backend_main.get_batch(batch["id"])
    assert result["successful"] == 1
    assert result["failed"] == 0
    assert result["skipped"] == 1


def test_duplicate_queue_entries_are_claimed_once(monkeypatch) -> None:
    calls = []

    def signup(identity):
        calls.append(identity.account_id)
        return type("Result", (), {"status": "SUCCESS", "account_id": identity.account_id})()

    monkeypatch.setattr(backend_main, "run_mock_signup", signup)
    batch = queued_batch(1)
    first = threading.Thread(target=backend_main.process_batch, args=(batch["id"],))
    second = threading.Thread(target=backend_main.process_batch, args=(batch["id"],))
    first.start()
    second.start()
    first.join(2)
    second.join(2)

    result = backend_main.get_batch(batch["id"])
    assert result["status"] == "COMPLETED"
    assert result["successful"] == 1
    assert len(calls) == 1


def test_api_reads_live_worker_progress(monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()

    def signup(identity):
        started.set()
        release.wait(1)
        return type("Result", (), {"status": "SUCCESS", "account_id": identity.account_id})()

    monkeypatch.setattr(backend_main, "run_mock_signup", signup)
    batch = queued_batch(2)
    worker = threading.Thread(target=backend_main.process_batch, args=(batch["id"],))
    worker.start()
    assert started.wait(1)
    current = backend_main.get_batch(batch["id"])
    assert current["status"] == "RUNNING"
    assert current["successful"] == 0
    release.set()
    worker.join(2)
    final = backend_main.get_batch(batch["id"])
    assert final["status"] == "COMPLETED"
    assert final["successful"] == 2


def test_multiple_batches_are_processed_independently(monkeypatch) -> None:
    monkeypatch.setattr(
        backend_main,
        "run_mock_signup",
        lambda identity: type("Result", (), {"status": "SUCCESS", "account_id": identity.account_id})(),
    )
    first_batch = queued_batch(2)
    second_batch = queued_batch(3)
    first_worker = threading.Thread(target=backend_main.process_batch, args=(first_batch["id"],))
    second_worker = threading.Thread(target=backend_main.process_batch, args=(second_batch["id"],))
    first_worker.start()
    second_worker.start()
    first_worker.join(2)
    second_worker.join(2)

    first_result = backend_main.get_batch(first_batch["id"])
    second_result = backend_main.get_batch(second_batch["id"])
    assert first_result["status"] == "COMPLETED"
    assert first_result["successful"] == 2
    assert second_result["status"] == "COMPLETED"
    assert second_result["successful"] == 3


def test_worker_ignores_already_completed_batch(monkeypatch) -> None:
    calls = []

    def signup(identity):
        calls.append(identity.account_id)
        return type("Result", (), {"status": "SUCCESS", "account_id": identity.account_id})()

    monkeypatch.setattr(backend_main, "run_mock_signup", signup)
    batch = backend_main.create_batch("ALREADY_DONE")
    update_batch(batch["id"], target=1, successful=1, status="COMPLETED")
    backend_main.process_batch(batch["id"])
    result = backend_main.get_batch(batch["id"])
    assert result["status"] == "COMPLETED"
    assert result["successful"] == 1
    assert calls == []


def test_worker_loop_processes_queued_batch(monkeypatch) -> None:
    monkeypatch.setattr(
        backend_main,
        "run_mock_signup",
        lambda identity: type("Result", (), {"status": "SUCCESS", "account_id": identity.account_id})(),
    )
    batch = backend_main.create_batch("QUEUE_TEST")
    update_batch(batch["id"], target=2)
    backend_main.pause_events[batch["id"]] = threading.Event()
    backend_main.stop_events[batch["id"]] = threading.Event()
    backend_main.transition_batch(batch["id"], "QUEUED", "test")
    backend_main.job_queue.put(batch["id"])

    worker = threading.Thread(target=backend_main.worker_loop, daemon=True)
    worker.start()
    wait_for_status(batch["id"], "COMPLETED")
    result = backend_main.get_batch(batch["id"])
    assert result["successful"] == 2


def test_progress_metrics_are_consistent() -> None:
    batch = backend_main.create_batch("PROGRESS_TEST")
    update_batch(batch["id"], target=0)
    progress = backend_main.calculate_batch_progress(batch["id"])
    assert progress["successful"] == 0
    assert progress["remaining"] == 0
    assert progress["progress_percent"] == 0

    update_batch(batch["id"], target=1, successful=1, failed=0, skipped=0, attempted=1, retries=0)
    progress = backend_main.calculate_batch_progress(batch["id"])
    assert progress["progress_percent"] == 100
    assert progress["remaining"] == 0

    update_batch(batch["id"], target=10, successful=3, failed=2, skipped=1, attempted=6, retries=2)
    progress = backend_main.calculate_batch_progress(batch["id"])
    assert 0 <= progress["progress_percent"] <= 100
    assert progress["remaining"] >= 0
    assert progress["progress_percent"] == 30


def test_retry_policy_uses_backoff_and_blocks_duplicates(monkeypatch) -> None:
    monkeypatch.setattr(backend_main, "RETRY_DELAY_SECONDS", 0.5)
    monkeypatch.setattr(backend_main, "RETRY_BACKOFF_MULTIPLIER", 2.0)
    monkeypatch.setattr(backend_main, "MAX_RETRY_DELAY_SECONDS", 2.0)
    assert backend_main.calculate_retry_delay(1) == 0.5
    assert backend_main.calculate_retry_delay(2) == 1.0
    assert backend_main.calculate_retry_delay(3) == 2.0
    assert backend_main.calculate_retry_delay(4) == 2.0
    assert backend_main.should_retry("FAILURE", "RUNNING", 1) is True
    assert backend_main.should_retry("TIMEOUT", "RUNNING", 1) is True
    assert backend_main.should_retry("DUPLICATE", "RUNNING", 1) is False
    assert backend_main.should_retry("LIMIT_REACHED", "RUNNING", 1) is False
    assert backend_main.should_retry("FAILURE", "CANCELLED", 1) is False


def test_google_sheet_export_uses_safe_fallback_row(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(google_sheets, "RESULTS_PATH", tmp_path / "mock_sheet.jsonl")
    monkeypatch.delenv("GOOGLE_SHEETS_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)

    google_sheets.append_result({
        "id": "acct-1",
        "name": "Alice Test",
        "test_id": "mock-001",
        "referral": "REF-123",
        "batch_id": "batch-123",
        "status": "SUCCESS",
        "error": "",
    })

    lines = (tmp_path / "mock_sheet.jsonl").read_text(encoding="utf-8").strip().splitlines()
    row = json.loads(lines[0])
    assert row["status"] == "SUCCESS"
    assert row["batch_id"] == "batch-123"
    assert row["name"] == "Alice Test"


def read_event(stream, timeout: float = 1) -> str:
    return asyncio.run(asyncio.wait_for(stream.body_iterator.__anext__(), timeout))


def test_sse_sends_initial_batch_state() -> None:
    batch = queued_batch(1)
    stream = asyncio.run(backend_main.batch_events(batch["id"]))
    try:
        event = read_event(stream)
        assert json.loads(event.removeprefix("data: ").strip())["id"] == batch["id"]
    finally:
        asyncio.run(stream.body_iterator.aclose())


def test_sse_sends_progress_and_completion_events(monkeypatch) -> None:
    monkeypatch.setattr(backend_main, "run_mock_signup", lambda identity: type("Result", (), {"status": "SUCCESS", "account_id": identity.account_id})())
    batch = queued_batch(1)
    stream = asyncio.run(backend_main.batch_events(batch["id"]))
    try:
        read_event(stream)
        backend_main.claim_queued_batch(batch["id"])
        assert json.loads(read_event(stream).removeprefix("data: ").strip())["status"] == "RUNNING"
        progress = backend_main.record_success(batch["id"], "ACCOUNT", "NUMBER")
        assert progress is not None
        event = read_event(stream)
        assert json.loads(event.removeprefix("data: ").strip())["successful"] == 1
        backend_main.transition_batch(batch["id"], "COMPLETED", "test")
        event = read_event(stream)
        assert json.loads(event.removeprefix("data: ").strip())["status"] == "COMPLETED"
    finally:
        asyncio.run(stream.body_iterator.aclose())


def test_sse_sends_failure_event() -> None:
    batch = queued_batch(1)
    stream = asyncio.run(backend_main.batch_events(batch["id"]))
    try:
        read_event(stream)
        backend_main.claim_queued_batch(batch["id"])
        read_event(stream)
        backend_main.update_batch(batch["id"], status="FAILED")
        event = read_event(stream)
        assert json.loads(event.removeprefix("data: ").strip())["status"] == "FAILED"
    finally:
        asyncio.run(stream.body_iterator.aclose())


def test_sse_delivers_pause_resume_and_cancel_events() -> None:
    batch = queued_batch(1)
    stream = asyncio.run(backend_main.batch_events(batch["id"]))
    try:
        read_event(stream)
        backend_main.claim_queued_batch(batch["id"])
        assert json.loads(read_event(stream).removeprefix("data: ").strip())["status"] == "RUNNING"
        backend_main.transition_batch(batch["id"], "PAUSED", "test")
        assert json.loads(read_event(stream).removeprefix("data: ").strip())["status"] == "PAUSED"
        backend_main.transition_batch(batch["id"], "RUNNING", "test")
        assert json.loads(read_event(stream).removeprefix("data: ").strip())["status"] == "RUNNING"
        backend_main.transition_batch(batch["id"], "STOPPING", "test")
        assert json.loads(read_event(stream).removeprefix("data: ").strip())["status"] == "STOPPING"
        backend_main.transition_batch(batch["id"], "CANCELLED", "test")
        assert json.loads(read_event(stream).removeprefix("data: ").strip())["status"] == "CANCELLED"
    finally:
        asyncio.run(stream.body_iterator.aclose())


def test_sse_supports_multiple_subscribers_and_disconnect_cleanup() -> None:
    batch = queued_batch(1)
    first = asyncio.run(backend_main.batch_events(batch["id"]))
    second = asyncio.run(backend_main.batch_events(batch["id"]))
    try:
        assert len(backend_main.subscribers[batch["id"]]) == 2
        assert json.loads(read_event(first).removeprefix("data: ").strip())["id"] == batch["id"]
        assert json.loads(read_event(second).removeprefix("data: ").strip())["id"] == batch["id"]
        backend_main.update_batch(batch["id"], failed=1)
        assert json.loads(read_event(first).removeprefix("data: ").strip())["failed"] == 1
        assert json.loads(read_event(second).removeprefix("data: ").strip())["failed"] == 1
    finally:
        asyncio.run(first.body_iterator.aclose())
        asyncio.run(second.body_iterator.aclose())
    assert batch["id"] not in backend_main.subscribers


def test_export_batch_csv_and_json() -> None:
    client = TestClient(app)
    batch = backend_main.create_batch("EXPORT_TEST")
    csv_res = client.get(f"/batches/{batch['id']}/export/csv")
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert "EXPORT_TEST" in csv_res.text

    json_res = client.get(f"/batches/{batch['id']}/export/json")
    assert json_res.status_code == 200
    data = json_res.json()
    assert data["batch"]["id"] == batch["id"]
    assert data["batch"]["referral"] == "EXPORT_TEST"


def test_workers_endpoint() -> None:
    client = TestClient(app)
    res = client.get("/workers")
    assert res.status_code == 200
    data = res.json()
    assert "active_worker_id" in data
    assert "queue_size" in data
    assert "recent_jobs" in data


def test_worker_terminates_immediately_on_limit_reached(monkeypatch) -> None:
    from worker.automation.signup_flow import SignupResult

    attempt_count = 0

    def mock_signup(identity):
        nonlocal attempt_count
        attempt_count += 1
        return SignupResult.limit_reached(identity.account_id, "This referral code has reached its maximum limit")

    monkeypatch.setattr(backend_main, "run_mock_signup", mock_signup)
    batch = queued_batch(100)
    backend_main.process_batch(batch["id"])

    result = backend_main.get_batch(batch["id"])
    # Batch terminates immediately and does not retry 100 times
    assert result["status"] in ("COMPLETED", "FAILED")
    assert attempt_count == 1


def test_worker_circuit_breaker_triggers_after_consecutive_failures(monkeypatch) -> None:
    monkeypatch.setenv("MAX_CONSECUTIVE_FAILURES", "5")
    monkeypatch.setattr(backend_main, "RETRY_DELAY_SECONDS", 0.0)
    from worker.automation.signup_flow import SignupResult

    attempt_count = 0

    def mock_signup(identity):
        nonlocal attempt_count
        attempt_count += 1
        return SignupResult.failure(identity.account_id, "Network failure")

    monkeypatch.setattr(backend_main, "run_mock_signup", mock_signup)
    batch = queued_batch(100)
    backend_main.process_batch(batch["id"])

    result = backend_main.get_batch(batch["id"])
    assert result["status"] in ("COMPLETED", "FAILED")
    assert result["failed"] == 5


def test_parallel_signups_do_not_overshoot_target(monkeypatch) -> None:
    monkeypatch.setenv("SIGNUP_CONCURRENCY", "8")
    monkeypatch.setenv("MAX_PARALLEL_SIGNUPS", "8")
    monkeypatch.setattr(
        backend_main,
        "run_mock_signup",
        lambda identity: type("Result", (), {"status": "SUCCESS", "account_id": identity.account_id, "error": "", "timestamp": ""})(),
    )
    batch = queued_batch(3)
    backend_main.process_batch(batch["id"])
    result = backend_main.get_batch(batch["id"])
    assert result["status"] == "COMPLETED"
    assert result["successful"] == 3


def test_already_registered_numbers_are_skipped_until_target(monkeypatch) -> None:
    phones = iter(["TAKEN1", "TAKEN2", "TAKEN3", "FRESH"])
    monkeypatch.setattr(backend_main, "claim_unique_phone", lambda batch_id: next(phones))

    def signup(identity):
        if identity.account_id.startswith("TAKEN"):
            return type("Result", (), {"status": "DUPLICATE", "account_id": identity.account_id, "error": "already registered", "timestamp": ""})()
        return type("Result", (), {"status": "SUCCESS", "account_id": identity.account_id, "error": "", "timestamp": ""})()

    monkeypatch.setattr(backend_main, "run_mock_signup", signup)
    batch = queued_batch(1)
    backend_main.process_batch(batch["id"])
    result = backend_main.get_batch(batch["id"])
    assert result["status"] == "COMPLETED"
    assert result["successful"] == 1
    assert result["skipped"] == 3
    assert result["failed"] == 0


def test_accounts_endpoint_works_without_jwt() -> None:
    with TestClient(app) as client:
        batch = client.post("/batches", json={"referral": "ACCOUNTS"}).json()
        response = client.get(f"/batches/{batch['id']}/accounts")
    assert response.status_code == 200
    assert response.json() == {"accounts": []}
    assert response.headers.get("x-content-type-options") == "nosniff"


def test_write_retry_on_locked_database(monkeypatch) -> None:
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return 7

    assert backend_main.with_write_retry(flaky) == 7
    assert calls["n"] == 2
