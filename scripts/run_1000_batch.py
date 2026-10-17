import os
import sys
import time

# Force live automation mode
os.environ["AUTOMATION_MODE"] = "live"
os.environ["ENABLE_DATA_STORAGE"] = "false"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.main import create_batch, start_batch, process_batch, get_batch

def run_referral_batch(code: str, target: int = 1000) -> dict:
    code = code.strip()
    print(f"\n{'=' * 60}")
    print(f"[*] Starting Batch for Referral Code: {code} (Target: {target})")
    print(f"{'=' * 60}")
    
    batch = create_batch(code)
    batch_id = batch["id"]
    start_batch(batch_id)
    
    t0 = time.time()
    try:
        process_batch(batch_id)
    except KeyboardInterrupt:
        print("\n[!] User interrupted batch execution.")
    elapsed = time.time() - t0
    
    final = get_batch(batch_id)
    print("\n" + "-" * 50)
    print(f"BATCH SUMMARY for {code} (in {elapsed:.1f}s):")
    print(f"Status:     {final['status']}")
    print(f"Successful: {final['successful']}/{final['target']}")
    print(f"Attempted:  {final['attempted']}")
    print(f"Failed:     {final['failed']}")
    print(f"Skipped:    {final['skipped']}")
    if final.get("error_message"):
        print(f"Note:       {final['error_message']}")
    print("-" * 50)
    return final

def main():
    if len(sys.argv) > 1:
        referral_codes = sys.argv[1:]
    else:
        # Prompt or use default
        try:
            user_input = input("Enter referral code(s) (comma or space-separated, or press Enter for default): ").strip()
        except (EOFError, KeyboardInterrupt):
            user_input = ""
        if user_input:
            import re
            referral_codes = [c.strip() for c in re.split(r"[\s,;]+", user_input) if c.strip()]
        else:
            referral_codes = ["100CRCLUBBOSUU11G"]

    print(f"[*] Queued {len(referral_codes)} referral(s) for sequential execution: {', '.join(referral_codes)}")
    
    for i, code in enumerate(referral_codes, 1):
        print(f"\n>>> Running Referral {i}/{len(referral_codes)}: {code}")
        run_referral_batch(code)
        if i < len(referral_codes):
            print("[*] Transitioning to next queued referral in 1 second...")
            time.sleep(1)

    print("\n[✓] All queued referral batches finished.")

if __name__ == "__main__":
    main()
