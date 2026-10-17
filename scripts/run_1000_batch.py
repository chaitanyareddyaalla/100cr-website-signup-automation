import os
import sys
import time

# Force live automation mode
os.environ["AUTOMATION_MODE"] = "live"
os.environ["ENABLE_DATA_STORAGE"] = "false"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.main import create_batch, start_batch, process_batch, get_batch

referral_code = "100CRCLUBBOSUU11G"
print(f"[*] Creating full 1,000-signup batch for referral: {referral_code} ...")
batch = create_batch(referral_code)
batch_id = batch["id"]
print(f"[*] Batch ID created: {batch_id} (Target: {batch['target']})")

print("[*] Starting batch ...")
start_batch(batch_id)

print("[*] Processing 1,000 signups in progress ...")
t0 = time.time()
process_batch(batch_id)
elapsed = time.time() - t0

final = get_batch(batch_id)
print("\n" + "=" * 50)
print(f"BATCH COMPLETE in {elapsed:.1f}s")
print(f"Status:     {final['status']}")
print(f"Successful: {final['successful']}/{final['target']}")
print(f"Failed:     {final['failed']}")
print(f"Retries:    {final['retries']}")
print(f"Skipped:    {final['skipped']}")
print("=" * 50)
