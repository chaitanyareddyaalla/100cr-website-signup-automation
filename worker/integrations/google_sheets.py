import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

RESULTS_PATH = Path(
    os.getenv("RESULTS_EXPORT_PATH")
    or (Path(__file__).resolve().parents[2] / "data" / "results_export.jsonl")
)
SHEET_COLUMNS = [
    "Phone Number",
    "Password",
    "Place",
    "Referral Code",
    "Language",
    "Status",
    "Timestamp",
    "ID",
    "Name",
    "Batch ID",
    "Error",
]


def _normalize_result_row(result: dict) -> dict:
    row = {
        "id": result.get("id", ""),
        "name": result.get("name", ""),
        "test_id": result.get("test_id", ""),
        "phone": result.get("phone", ""),
        "password": result.get("password", ""),
        "place": result.get("place", ""),
        "referral": result.get("referral", ""),
        "language": result.get("language", ""),
        "batch_id": result.get("batch_id", ""),
        "status": result.get("status", ""),
        "error": result.get("error", ""),
        "created_at": result.get("created_at") or datetime.now(timezone.utc).isoformat(),
    }
    if not row["status"]:
        row["status"] = "UNKNOWN"
    return row


def _get_gspread_client(credentials_source: str):
    import gspread

    trimmed = credentials_source.strip()
    if trimmed.startswith("{") and trimmed.endswith("}"):
        info = json.loads(trimmed)
        return gspread.service_account_from_dict(info)
    return gspread.service_account(filename=credentials_source)


def append_result(result: dict) -> None:
    """Export result row. Google Sheets is optional and failure-isolated."""
    row = _normalize_result_row(result)
    sheet_id = os.getenv("GOOGLE_SHEETS_ID")
    credentials_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_SERVICE_ACCOUNT_INFO")

    if sheet_id and credentials_path:
        try:
            _append_google_row(sheet_id, credentials_path, row)
            return
        except Exception as exc:
            logger.warning(f"Google Sheets export skipped/failed (falling back to file): {exc}")

    try:
        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with RESULTS_PATH.open("a", encoding="utf-8") as output:
            output.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
    except Exception as exc:
        logger.error(f"Failed to append result to local JSONL backup: {exc}")


def _append_google_row(sheet_id: str, credentials_path: str, row: dict) -> None:
    client = _get_gspread_client(credentials_path)
    worksheet_name = os.getenv("GOOGLE_SHEETS_WORKSHEET", "Results")
    sh = client.open_by_key(sheet_id)
    try:
        worksheet = sh.worksheet(worksheet_name)
    except Exception:
        try:
            worksheet = sh.add_worksheet(title=worksheet_name, rows=1000, cols=len(SHEET_COLUMNS))
        except Exception:
            worksheet = sh.sheet1

    if not worksheet.get_all_values():
        worksheet.append_row(SHEET_COLUMNS)
    worksheet.append_row([
        row.get("phone") or row.get("test_id", ""),
        row.get("password", ""),
        row.get("place", ""),
        row.get("referral", ""),
        row.get("language", ""),
        row.get("status", ""),
        row["created_at"],
        row.get("id", ""),
        row.get("name", ""),
        row.get("batch_id", ""),
        row.get("error", ""),
    ])
