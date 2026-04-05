"""
Run this on Windows to inspect what's actually on the NVIDIA Workday page.
It opens the browser, waits 10 seconds for JS to load, then prints all 
clickable elements so we can find the exact Apply button selector.
"""
from playwright.sync_api import sync_playwright
import time

url = "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/US-CA-Santa-Clara/Senior-Systems-Software-Engineer---Autonomous-Vehicles_JR2015666"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 900},
    )
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    page = context.new_page()
    
    print("Loading NVIDIA Workday page...")
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    print("Waiting 8s for JS to render...")
    time.sleep(8)
    
    print(f"\nPage title: {page.title()}")
    print(f"Page URL: {page.url}")
    
    # Find all buttons and links
    print("\n--- All buttons ---")
    buttons = page.locator("button").all()
    for b in buttons[:20]:
        try:
            txt = b.inner_text().strip()
            da = b.get_attribute("data-automation") or ""
            cls = b.get_attribute("class") or ""
            if txt or da:
                print(f"  button: text='{txt}' data-automation='{da}'")
        except: pass
    
    print("\n--- All links ---")
    links = page.locator("a").all()
    for l in links[:20]:
        try:
            txt = l.inner_text().strip()
            da = l.get_attribute("data-automation") or ""
            href = l.get_attribute("href") or ""
            if txt and len(txt) < 50:
                print(f"  link: text='{txt}' data-automation='{da}' href='{href[:50]}'")
        except: pass

    print("\n--- Elements with 'apply' in text or attributes ---")
    apply_els = page.locator("[data-automation*='apply'], [class*='apply'], button:has-text('Apply'), a:has-text('Apply')").all()
    for el in apply_els[:10]:
        try:
            tag = el.evaluate("el => el.tagName")
            txt = el.inner_text().strip()
            da = el.get_attribute("data-automation") or ""
            print(f"  {tag}: text='{txt}' data-automation='{da}'")
        except: pass
    
    input("\nPress Enter to close browser...")
    browser.close()
