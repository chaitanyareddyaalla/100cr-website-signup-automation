import sys
from playwright.sync_api import sync_playwright

# Set stdout encoding to utf-8
sys.stdout.reconfigure(encoding="utf-8")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://www.100crorescompany.com/signup", wait_until="networkidle", timeout=30000)
    print("Page Title:", page.title())
    print("Page URL:", page.url)

    inputs = page.query_selector_all("input, select, textarea")
    print(f"\n--- Form Controls ({len(inputs)}) ---")
    for inp in inputs:
        name = inp.get_attribute("name")
        inp_type = inp.get_attribute("type")
        placeholder = inp.get_attribute("placeholder")
        inp_id = inp.get_attribute("id")
        print(f"  Field: tag={inp.evaluate('e => e.tagName')}, name={name}, id={inp_id}, type={inp_type}, placeholder={placeholder}")

    buttons = page.query_selector_all("button")
    print(f"\n--- Buttons ({len(buttons)}) ---")
    for b in buttons:
        b_type = b.get_attribute("type")
        b_text = b.inner_text().strip().replace("\n", " ")
        print(f"  Button: type={b_type}, text='{b_text}'")

    browser.close()
