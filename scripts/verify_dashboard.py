#!/usr/bin/env python3
import os
import time
from playwright.sync_api import sync_playwright

# Setup screenshot paths in artifacts directory
ARTIFACTS_DIR = "/Users/thirsty/.gemini/antigravity/brain/e55a41c0-8c33-4440-ba50-14eeee988fce"
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

scheduler_img = os.path.join(ARTIFACTS_DIR, "dashboard_scheduler.png")
calendar_img = os.path.join(ARTIFACTS_DIR, "dashboard_calendar.png")
kanban_img = os.path.join(ARTIFACTS_DIR, "dashboard_kanban.png")
modal_img = os.path.join(ARTIFACTS_DIR, "dashboard_modal.png")

def run():
    print("Starting Playwright Verification...")
    with sync_playwright() as p:
        # Launch headless browser
        browser = p.chromium.launch(headless=True)
        # Set a standard desktop viewport
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        
        # Navigate to local dashboard
        print("Navigating to http://localhost:8080/...")
        try:
            page.goto("http://localhost:8080/", timeout=10000)
        except Exception as e:
            print(f"Error navigating: {e}")
            browser.close()
            return
            
        time.sleep(2) # Allow canvas and fonts to render
        
        # 1. Capture Scheduler View
        print("Capturing Scheduler View...")
        page.screenshot(path=scheduler_img)
        
        # 2. Click Calendar view tab and capture
        print("Navigating to Calendar View...")
        page.locator("text=Calendar View").click()
        time.sleep(1)
        page.screenshot(path=calendar_img)
        
        # 3. Click Kanban board tab and capture
        print("Navigating to Kanban Board...")
        page.locator("text=Kanban Board").click()
        time.sleep(1)
        page.screenshot(path=kanban_img)
        
        # 4. Open X Connection modal
        print("Opening X Connection Modal...")
        page.locator("text=Composer").click()
        time.sleep(0.5)
        page.locator("id=btn-x").click()
        time.sleep(1)
        page.screenshot(path=modal_img)
        
        print("Dashboard views captured successfully!")
        browser.close()

if __name__ == "__main__":
    run()
