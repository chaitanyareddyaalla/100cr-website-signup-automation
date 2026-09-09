"""Local Google Sheets connection diagnostic and test script."""

import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

import gspread
from worker.integrations.google_sheets import SHEET_COLUMNS, _get_gspread_client


def main() -> int:
    print("\n=======================================================")
    print("  GOOGLE SHEETS INTEGRATION LOCAL VERIFICATION")
    print("=======================================================\n")

    sheet_id = os.getenv("GOOGLE_SHEETS_ID", "").strip()
    worksheet_name = os.getenv("GOOGLE_SHEETS_WORKSHEET", "Results").strip()
    creds_source = (
        os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        or os.getenv("GOOGLE_SERVICE_ACCOUNT_INFO", "").strip()
    )

    print(f"[*] Target Sheet ID: {sheet_id or '[NOT SET]'}")
    print(f"[*] Target Worksheet: {worksheet_name}")
    print(f"[*] Credentials Source: {creds_source or '[NOT SET]'}\n")

    if not sheet_id:
        print("[!] ERROR: GOOGLE_SHEETS_ID is not configured in .env")
        return 1

    if not creds_source:
        print("[!] ERROR: Google Service Account credentials are not configured.")
        print("\n--> How to configure:")
        print("1. Download your Google Cloud Service Account JSON key.")
        print("2. Save it in the project root as 'service-account.json'.")
        print("3. In .env, set:")
        print("   GOOGLE_SERVICE_ACCOUNT_JSON=service-account.json")
        print("4. Share your Google Sheet (Editor access) with the 'client_email' found inside service-account.json.")
        return 1

    # Check if file exists if creds_source is a path
    if not (creds_source.startswith("{") and creds_source.endswith("}")):
        creds_file = Path(creds_source)
        if not creds_file.is_absolute():
            creds_file = PROJECT_ROOT / creds_file
        if not creds_file.exists():
            print(f"[!] ERROR: Credentials file not found at: {creds_file}")
            print("\n--> To resolve:")
            print(f"    Please place your Google Cloud Service Account key JSON file at:")
            print(f"    {creds_file}")
            print("    and make sure the Google Sheet is shared with your Service Account email address as Editor.")
            return 1
        creds_source = str(creds_file)

    try:
        print("[*] Authenticating with Google Sheets API...")
        client = _get_gspread_client(creds_source)
        
        # Read client email from credentials if available
        service_email = getattr(client.auth, "signer_email", None) or "Service Account"
        print(f"[+] Successfully authenticated as: {service_email}")

        print(f"[*] Opening Spreadsheet with ID: {sheet_id} ...")
        sh = client.open_by_key(sheet_id)
        print(f"[+] Connected to Spreadsheet: '{sh.title}'")

        print(f"[*] Accessing worksheet '{worksheet_name}'...")
        try:
            worksheet = sh.worksheet(worksheet_name)
        except Exception:
            print(f"[*] Worksheet '{worksheet_name}' not found. Creating it...")
            try:
                worksheet = sh.add_worksheet(title=worksheet_name, rows=1000, cols=len(SHEET_COLUMNS))
                print(f"[+] Created worksheet '{worksheet_name}'.")
            except Exception:
                print("[*] Fallback to primary sheet1...")
                worksheet = sh.sheet1

        # Check or add headers
        values = worksheet.get_all_values()
        if not values:
            print(f"[*] Sheet is empty. Writing headers: {SHEET_COLUMNS}")
            worksheet.append_row(SHEET_COLUMNS)
            print("[+] Headers written successfully.")
        else:
            print(f"[+] Found {len(values)} existing row(s) in worksheet.")

        # Append a test verification row
        print("[*] Writing test verification row...")
        from datetime import datetime, timezone
        test_row = [
            "+919876543210",               # Phone Number
            "TestPassword123!",            # Password
            "LocalTest",                   # Place
            "TESTREF",                     # Referral Code
            "en",                          # Language
            "LOCAL_VERIFIED",              # Status
            datetime.now(timezone.utc).isoformat(), # Timestamp
            "diag-test-1",                 # ID
            "Local Diagnostic Test",       # Name
            "batch-local-diag",            # Batch ID
            "",                            # Error
        ]
        worksheet.append_row(test_row)
        print("[+] Test row appended successfully!")
        print("\n=======================================================")
        print("  SUCCESS: Google Sheets integration is verified & working!")
        print("=======================================================\n")
        return 0

    except Exception as exc:
        print(f"\n[!] Connection or Permission Error: {exc}")
        print("\n--> Troubleshooting Checklist:")
        print("1. Did you share the Google Sheet with the Service Account email?")
        print("   URL: https://docs.google.com/spreadsheets/d/1hOKjFmrLwvcPPLi-h0aQj_WSkkCMttE9PHJE6A8C-c4/edit")
        print("   Click 'Share' -> Paste the service account email -> Set role to 'Editor'.")
        print("2. Is the Google Sheets API and Google Drive API enabled in your Google Cloud Console?")
        return 1


if __name__ == "__main__":
    sys.exit(main())
