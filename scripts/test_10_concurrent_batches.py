"""
Verification script: Test 10 concurrent referral batches running in parallel
simulating multiple devices/tabs without lags, clashes, or deadlocks.
"""
import os
import sys
import time
import threading
from pathlib import Path

# Ensure root directory is on path and set mock mode for local test
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["AUTOMATION_MODE"] = "mock"

from backend.app import main as backend_main
from worker.automation.signup_flow import SignupResult

def run_test():
    print("=" * 60)
    print("TEST: Running 10 Concurrent Referrals in Parallel")
    print("=" * 60)

    # Initialize DB
    backend_main.initialize_database()
    backend_main.global_used_phones.clear()

    # Track all used phones across all 10 batches to verify 0 collisions
    used_phones_lock = threading.Lock()
    all_used_phones = set()
    collisions = []

    def mock_signup(identity):
        phone = identity.phone
        with used_phones_lock:
            if phone in all_used_phones:
                collisions.append(phone)
            all_used_phones.add(phone)
        # Verify 10 digits
        assert len(phone) == 10, f"Invalid phone length: {phone}"
        assert phone.isdigit(), f"Phone not digits: {phone}"
        # Simulate fast API response (2-5ms)
        time.sleep(0.003)
        return SignupResult.success(account_id=phone, phone=phone)

    # Monkeypatch signup flow
    backend_main.run_mock_signup = mock_signup

    num_batches = 10
    target_per_batch = 50  # 50 per batch = 500 signups total across 10 batches
    referrals = [f"REFDEVICE{i+1:02d}CODE" for i in range(num_batches)]

    print(f"[*] Creating {num_batches} batches with distinct referral codes...")
    batch_ids = []
    for ref in referrals:
        b = backend_main.create_batch(ref)
        batch_ids.append(b["id"])
        # Set target for this test run
        backend_main.update_batch(b["id"], target=target_per_batch)

    print(f"[+] Created {len(batch_ids)} batches. Starting all 10 concurrently...")
    start_time = time.monotonic()

    # Launch all 10 batches in parallel threads simulating 10 distinct devices/workers
    threads = []
    for bid in batch_ids:
        t = threading.Thread(target=backend_main.process_batch, args=(bid,), name=f"device-{bid[:8]}")
        threads.append(t)
        # Put batch into RUNNING state
        backend_main.start_batch(bid)
        t.start()

    # Monitor progress across all 10 batches while they are running
    all_done = False
    max_wait = 30.0  # seconds
    deadline = time.monotonic() + max_wait

    print("\n--- Live Concurrency Progress Monitor ---")
    while time.monotonic() < deadline and not all_done:
        statuses = []
        progresses = []
        successes = []
        all_done = True
        for bid in batch_ids:
            b = backend_main.get_batch(bid)
            statuses.append(b["status"])
            progresses.append(f"{b['progress_percent']}%")
            successes.append(b["successful"])
            if b["status"] not in ("COMPLETED", "FAILED", "CANCELLED"):
                all_done = False

        elapsed = time.monotonic() - start_time
        print(f"[{elapsed:.1f}s] Statuses: {statuses[:5]}... | Successes: {sum(successes)}/{num_batches * target_per_batch}")
        if all_done:
            break
        time.sleep(0.5)

    # Wait for all threads to cleanly finish
    for t in threads:
        t.join(timeout=5.0)

    total_time = time.monotonic() - start_time
    print(f"\n[*] All batches finished in {total_time:.2f} seconds.")

    # Validation Checks
    print("\n--- Validation Results ---")
    total_successful = 0
    all_completed = True

    for i, bid in enumerate(batch_ids):
        b = backend_main.get_batch(bid)
        print(f"Batch {i+1} ({b['referral']}): Status={b['status']}, Progress={b['progress_percent']}%, Success={b['successful']}, Failed={b['failed']}, Skipped={b['skipped']}")
        total_successful += b["successful"]
        if b["status"] != "COMPLETED":
            all_completed = False

    print("\n" + "=" * 60)
    print(f"Total Signups Completed: {total_successful} / {num_batches * target_per_batch}")
    print(f"Total Unique Numbers Generated: {len(all_used_phones)}")
    print(f"Phone Collisions / Clashes: {len(collisions)}")
    print("=" * 60)

    assert all_completed, "ERROR: Not all 10 batches completed to 100%!"
    assert total_successful == num_batches * target_per_batch, f"ERROR: Expected {num_batches * target_per_batch} successful signups, got {total_successful}"
    assert len(collisions) == 0, f"ERROR: Found {len(collisions)} phone collisions between concurrent batches!"
    assert len(all_used_phones) == total_successful, "ERROR: Used phone count does not match total successful count!"

    print("\n>>> ALL 10 CONCURRENT BATCHES COMPLETED SUCCESSFULLY WITH 0 LAGS AND 0 CLASHES! <<<")

if __name__ == "__main__":
    run_test()
