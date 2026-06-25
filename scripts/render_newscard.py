#!/usr/bin/env python3
import os
import sys
import tempfile
import pathlib
from datetime import datetime

def render_newscard(deal, save_path):
    """
    Renders an HTML newscard template to an image using Playwright.
    deal: dictionary with keys 'startup', 'amount', 'stage', 'industry', 'investors', 'summary'
    save_path: absolute path where the rendered image should be saved
    """
    print(f"Rendering newscard for {deal.get('startup')} via Playwright...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    template_path = os.path.join(project_root, "templates", "newscard.html")
    
    if not os.path.exists(template_path):
        print(f"Error: Template not found at {template_path}")
        return False
        
    with open(template_path, "r", encoding="utf-8") as f:
        template_content = f.read()
        
    # Get absolute path for logo
    logo_path = os.path.join(project_root, "assets", "TheInvestor.png")
    logo_uri = pathlib.Path(logo_path).as_uri()
    
    # Format today's date
    date_str = datetime.now().strftime("%B %d, %Y")
    
    # Prepare dynamic values
    startup = deal.get("startup", "Startup")
    amount = deal.get("amount", "Undisclosed")
    stage = deal.get("stage", "Undisclosed")
    
    # Handle industry/keywords
    industry = "Technology"
    if deal.get("keywords"):
        if isinstance(deal["keywords"], list) and len(deal["keywords"]) > 0:
            industry = deal["keywords"][0].title()
        elif isinstance(deal["keywords"], str):
            industry = deal["keywords"].split(",")[0].strip().title()
            
    investors = deal.get("investors", "Undisclosed")
    summary = deal.get("summary", "")
    
    # Clean up summary to fit nicely in 2-3 lines
    if len(summary) > 180:
        summary = summary[:177] + "..."
        
    # Replace placeholders
    html_content = template_content
    html_content = html_content.replace("{logo_path}", logo_uri)
    html_content = html_content.replace("{date}", date_str)
    html_content = html_content.replace("{startup}", startup)
    html_content = html_content.replace("{amount}", amount)
    html_content = html_content.replace("{stage}", stage)
    html_content = html_content.replace("{industry}", industry)
    html_content = html_content.replace("{investors}", investors)
    html_content = html_content.replace("{summary}", summary)
    
    # Write to a temporary HTML file
    temp_fd, temp_html_path = tempfile.mkstemp(suffix=".html")
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        # Use Playwright to capture screenshot
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            # Launch headless browser
            browser = p.chromium.launch(headless=True)
            # Create page with 1080x1350 dimensions
            page = browser.new_page(viewport={"width": 1080, "height": 1350})
            
            # Load the local HTML file
            page.goto(pathlib.Path(temp_html_path).as_uri())
            
            # Wait for images and web fonts to load
            page.wait_for_load_state("networkidle")
            
            # Capture the screenshot of the whole viewport
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            page.screenshot(path=save_path, type="jpeg", quality=90, full_page=True)
            browser.close()
            
        print(f"Successfully rendered and saved newscard to: {save_path}")
        return True
        
    except Exception as e:
        print(f"Error during Playwright rendering: {e}")
        return False
    finally:
        # Clean up temporary file
        if os.path.exists(temp_html_path):
            os.remove(temp_html_path)

if __name__ == "__main__":
    # Test script usage
    test_deal = {
        "startup": "The Investor",
        "amount": "$10 Million",
        "stage": "Series A",
        "keywords": ["Fintech", "Investment"],
        "investors": "Vanguard, Tiger Global",
        "summary": "The Investor is a premium capital briefing platform that delivers curated venture funding news and family office insights to high-net-worth subscribers."
    }
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    test_save_path = os.path.join(project_root, "NewsReport", "images", "test-newscard.jpg")
    
    success = render_newscard(test_deal, test_save_path)
    if success:
        print(f"Test card generated at: {test_save_path}")
    else:
        print("Failed to generate test card.")
