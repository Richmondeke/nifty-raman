#!/usr/bin/env python3
import os
import sys
import tempfile
import pathlib
import requests
from datetime import datetime

def download_image(url, save_path):
    try:
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(res.content)
            return True
    except Exception as e:
        print(f"Error downloading image {url}: {e}")
    return False

def resolve_deal_image(deal, project_root):
    startup = deal.get("startup", "startup").replace(" ", "_")
    images_dir = os.path.join(project_root, "NewsReport", "images")
    os.makedirs(images_dir, exist_ok=True)
    
    # 1. Check if we have a scraped article image
    url = deal.get("article_image_url")
    if url:
        save_path = os.path.join(images_dir, f"{startup}-scraped.jpg")
        print(f"Attempting to download news image for {startup} from: {url}...")
        if download_image(url, save_path):
            return save_path
            
    # 2. Try AI generation via Gemini Imagen
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=gemini_key)
            
            # Extract key person name if available
            summary = deal.get("summary", "")
            person_name = "None"
            if len(summary) > 20:
                extractor_prompt = f"Extract the name of the main founder or key person mentioned in this news summary: '{summary}'. If a person is mentioned, output ONLY their name. If no person is mentioned, output 'None'."
                response = client.models.generate_content(model="gemini-2.5-flash", contents=extractor_prompt)
                person_name = response.text.strip()
                
            industry = "Technology"
            if deal.get("keywords"):
                if isinstance(deal["keywords"], list) and len(deal["keywords"]) > 0:
                    industry = deal["keywords"][0]
                elif isinstance(deal["keywords"], str):
                    industry = deal["keywords"].split(",")[0].strip()
                    
            if person_name and person_name.lower() != "none" and len(person_name) < 50:
                prompt = f"A professional editorial headshot portrait photo of {person_name}, founder of {deal.get('startup')}. Clean white background, realistic professional photography, sharp focus, natural lighting, Satoshi style."
                print(f"Found person '{person_name}' in summary. Generating portrait...")
            else:
                prompt = f"A clean, minimal, high-end professional commercial photo representing {deal.get('startup')} (in the {industry} sector). Plain white background, studio lighting, product shot style, no text, clean composition."
                print(f"No person found in summary. Generating conceptual image...")
                
            save_path = os.path.join(images_dir, f"{startup}-ai-generated.jpg")
            img_res = client.models.generate_images(
                model='imagen-3.0-generate-002',
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="16:9"
                )
            )
            
            if img_res.generated_images:
                image_bytes = img_res.generated_images[0].image.image_bytes
                with open(save_path, "wb") as f:
                    f.write(image_bytes)
                print(f"Successfully generated AI image for {startup}")
                return save_path
        except Exception as e:
            print(f"Failed to generate AI image for {startup}: {e}")
            
    # 3. Fallback: use investor_spotlight.png or standard logo
    fallback = os.path.join(project_root, "assets", "investor_spotlight.png")
    if os.path.exists(fallback):
        return fallback
    return os.path.join(project_root, "assets", "TheInvestor.png")

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
    
    # Resolve the deal featured image
    deal_image_path = resolve_deal_image(deal, project_root)
    deal_image_uri = pathlib.Path(deal_image_path).as_uri() if deal_image_path else ""
    
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
    html_content = html_content.replace("{deal_image}", deal_image_uri)
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
