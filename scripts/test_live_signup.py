import sys
import time
import json
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

def on_request(req):
    if "api" in req.url or "auth" in req.url or "signup" in req.url:
        print(f"\n[>>> REQUEST] {req.method} {req.url}")
        print(f"  Post Data: {req.post_data}")

def on_response(res):
    if "api" in res.url or "auth" in res.url or "signup" in res.url:
        print(f"\n[<<< RESPONSE] HTTP {res.status} {res.url}")
        try:
            print(f"  Body: {res.text()}")
        except Exception as e:
            print(f"  Body read error: {e}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    page.on("request", on_request)
    page.on("response", on_response)

    print("[*] Navigating to https://www.100crorescompany.com/signup ...")
    page.goto("https://www.100crorescompany.com/signup", wait_until="networkidle", timeout=30000)

    print("[*] Filling signup form...")
    page.fill("#name", "Chaitanya Reddy")
    page.fill("#phone", "9876543210")
    page.fill("#place", "Hyderabad")
    page.fill("#password", "SecurePass@123")
    page.fill("#referralCode", "100CRCLUBW9PKQ69N")

    print("[*] Clicking 'Create Account'...")
    page.click("button[type='submit']")

    time.sleep(4)
    browser.close()
