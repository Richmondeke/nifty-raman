#!/usr/bin/env python3
import os
import sys
import tempfile
import pathlib
import smtplib
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime
import requests
import urllib.parse

# Import render component
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from render_newscard import ensure_playwright

def render_template_to_image(deal, save_path, template_name):
    """
    Renders a given HTML template with mock data using Playwright.
    """
    print(f"Rendering {template_name} to {save_path}...")
    if not ensure_playwright():
        print("Skipping Playwright render: environment setup failed.")
        return False
        
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    template_path = os.path.join(project_root, "templates", template_name)
    
    if not os.path.exists(template_path):
        print(f"Error: Template not found at {template_path}")
        return False
        
    with open(template_path, "r", encoding="utf-8") as f:
        template_content = f.read()
        
    # Get absolute path for logo
    logo_path = os.path.join(project_root, "assets", "TheInvestor.png")
    logo_uri = pathlib.Path(logo_path).as_uri()
    
    # Placeholders replacement
    html_content = template_content
    html_content = html_content.replace("{logo_path}", logo_uri)
    html_content = html_content.replace("{logo_uri}", logo_uri)
    
    # Replace standard variables
    for key, val in deal.items():
        html_content = html_content.replace(f"{{{key}}}", str(val))
        
    # Standard date fallback
    html_content = html_content.replace("{date}", datetime.now().strftime("%B %d, %Y"))
    html_content = html_content.replace("{date_time}", datetime.now().strftime("%B %d, %Y | 18:00 WAT"))
    
    # Write to a temporary HTML file
    temp_fd, temp_html_path = tempfile.mkstemp(suffix=".html")
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1080, "height": 1350})
            page.goto(pathlib.Path(temp_html_path).as_uri())
            page.wait_for_load_state("networkidle")
            
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            page.screenshot(path=save_path, type="jpeg", quality=90, full_page=True)
            browser.close()
            
        print(f"Successfully rendered: {save_path}")
        return True
    except Exception as e:
        print(f"Failed to render {template_name}: {e}")
        return False
    finally:
        if os.path.exists(temp_html_path):
            os.remove(temp_html_path)

def send_design_email(subject, item_name, image_path, recipient):
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    
    if not gmail_user or not gmail_password:
        print("Missing GMAIL credentials. Cannot send email.")
        return
        
    html_content = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>The Investor Design Showcase</title>
  <style type="text/css">
    @import url('https://api.fontshare.com/v2/css?f[]=satoshi@900,700,500,400&display=swap');
    body {{
      margin: 0;
      padding: 0;
      width: 100% !important;
      background-color: #FFFFFF;
      font-family: 'Satoshi', 'Helvetica Neue', Arial, sans-serif;
    }}
  </style>
</head>
<body style="margin: 0; padding: 0; background-color: #FFFFFF; color: #000000;">
  <center>
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #FFFFFF; padding: 40px 0;">
      <tr>
        <td align="center" valign="top">
          <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #FFFFFF; border: 3px solid #000000; box-shadow: 8px 8px 0px #000000;">
            <tr>
              <td align="center" valign="top" style="background-color: #000000; padding: 30px 20px;">
                <h1 style="font-family: 'Satoshi', Arial, sans-serif; color: #7ED957; font-size: 24px; font-weight: 900; text-transform: uppercase; letter-spacing: 2px; margin: 0;">
                  DESIGN REVISION
                </h1>
                <p style="font-family: 'Satoshi', Arial, sans-serif; color: #FFFFFF; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin: 10px 0 0 0;">
                  The Investor Branding Layouts
                </p>
              </td>
            </tr>
            <tr>
              <td align="left" valign="top" style="padding: 40px 40px 20px 40px; line-height: 1.6;">
                <h2 style="font-family: 'Satoshi', Arial, sans-serif; font-size: 22px; color: #000000; margin: 0 0 20px 0; font-weight: 900; text-transform: uppercase; letter-spacing: -0.5px; border-bottom: 3px solid #000000; padding-bottom: 10px;">
                  {item_name} Layout
                </h2>
                <div style="font-family: 'Satoshi', Arial, sans-serif; font-size: 16px; color: #000000; margin: 0; line-height: 1.6; font-weight: 500;">
                  Here is the redesigned layout for <strong>{item_name}</strong>, featuring custom grid structure, high-end shape geometry, and investor brand colors.
                </div>
              </td>
            </tr>
            <tr>
              <td align="center" valign="top" style="padding: 20px 40px;">
                <img src="cid:showcase_card" alt="Redesigned Card" style="width: 100%; max-width: 520px; height: auto; display: block; border: 3px solid #000000;" />
              </td>
            </tr>
            <tr>
              <td align="center" valign="top" style="background-color: #000000; padding: 40px; border-top: 3px solid #000000;">
                <p style="font-family: 'Satoshi', Arial, sans-serif; color: #FFFFFF; font-size: 18px; font-weight: 900; margin: 0 0 15px 0; letter-spacing: 2px; text-transform: uppercase;">
                  The Investor
                </p>
                <table border="0" cellpadding="0" cellspacing="0">
                  <tr>
                    <td align="center" style="background-color: #7ED957; border: 2px solid #000000; padding: 10px 24px;">
                      <a href="#" target="_blank" style="font-family: 'Satoshi', Arial, sans-serif; font-size: 14px; color: #000000; font-weight: 900; text-decoration: none; display: inline-block; text-transform: uppercase; letter-spacing: 1px;">
                        The Investor
                      </a>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </center>
</body>
</html>"""

    print(f"Sending email to {recipient} for {item_name}...")
    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(gmail_user, gmail_password)
        
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = f"The Investor <{gmail_user}>"
        msg['To'] = recipient
        
        msg_related = MIMEMultipart('related')
        msg.attach(msg_related)
        
        msg_html = MIMEText(html_content, 'html')
        msg_related.attach(msg_html)
        
        if os.path.exists(image_path):
            with open(image_path, 'rb') as f:
                img_data = f.read()
                
                # 1. Inline version
                msg_img_inline = MIMEImage(img_data)
                msg_img_inline.add_header('Content-ID', '<showcase_card>')
                msg_related.attach(msg_img_inline)
                
                # 2. Attachment version
                msg_img_attach = MIMEImage(img_data)
                msg_img_attach.add_header('Content-Disposition', 'attachment', filename=os.path.basename(image_path))
                msg.attach(msg_img_attach)
                
        server.sendmail(gmail_user, recipient, msg.as_string())
        print(f"Successfully dispatched: {item_name}")
        server.quit()
    except Exception as e:
        print(f"Failed to send email for {item_name}: {e}")

def get_pinterest_image_or_fallback(query, fallback_url):
    try:
        from pinterest_search import query_pinterest_search
        pins = query_pinterest_search(query, limit=1)
        if pins and pins[0].get("image_url"):
            print(f"Pinterest Search match for '{query}': {pins[0]['image_url']}")
            return pins[0]["image_url"]
    except Exception as e:
        print(f"Error fetching from Pinterest for '{query}': {e}")
    return fallback_url

def get_wikipedia_portrait(name):
    print(f"Fetching Wikipedia portrait for: {name}...")
    try:
        formatted_name = urllib.parse.quote(name.strip().replace(" ", "_"))
        url = f"https://en.wikipedia.org/w/api.php?action=query&titles={formatted_name}&prop=pageimages&format=json&pithumbsize=1000"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            pages = data.get("query", {}).get("pages", {})
            for page_id, page in pages.items():
                if "thumbnail" in page:
                    img_url = page["thumbnail"]["source"]
                    print(f"Wikipedia portrait found: {img_url}")
                    return img_url
    except Exception as e:
        print(f"Error fetching Wikipedia portrait: {e}")
    return None

def fetch_live_data_via_gemini():
    """
    Uses Gemini API with Google Search to fetch real live data for:
    - Daily Deal (Tech venture fundraising round in the last 7 days)
    - Breaking Deal (Tech venture fundraising round or M&A in the last 48 hours)
    - Job Role (Real remote/hybrid tech VC or AI job)
    - Event (Real upcoming finance, tech, startup or family office networking event in 2026)
    - Lifestyle (Real luxury item like Rolex/AP watch or sports car with pricing and specs)
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY not found in environment. Using fallback mock data.")
        return None
        
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
    except Exception as e:
        print(f"Failed to import/initialize Gemini Client: {e}. Using fallback mock data.")
        return None

    data = {}
    
    # 1. Fetch Daily Deal
    print("Fetching live Daily Deal data...")
    prompt_daily = """
    Search for a real, major tech/AI startup fundraising round (e.g. seed, Series A/B/C/D/E/F) announced within the last 7 days.
    Find one with a known startup name, amount, stage, industry, and investors.
    Format your response strictly as a JSON object with keys:
    "startup", "amount", "stage", "industry", "investors", "summary"
    Ensure "summary" is 2-3 sentences describing the startup's product and what they do. Do not include markdown code block ticks.
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_daily,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        text = response.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        data["daily_deal"] = json.loads(text)
    except Exception as e:
        print(f"Error fetching live daily deal: {e}")

    # 2. Fetch Breaking Deal
    print("Fetching live Breaking Deal data...")
    prompt_breaking = """
    Search for a very recent, major tech startup funding announcement, acquisition, or IPO within the last 48 hours.
    Format your response strictly as a JSON object with keys:
    "startup", "amount", "stage", "industry", "investors", "summary"
    Ensure "summary" is a high-impact, 2-3 sentence overview of the news. Do not include markdown code block ticks.
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_breaking,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        text = response.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        data["breaking_deal"] = json.loads(text)
    except Exception as e:
        print(f"Error fetching live breaking deal: {e}")

    # 3. Fetch Job Role
    print("Fetching live Job Role data...")
    prompt_job = """
    Search for a real, active remote or hybrid venture capital analyst/associate job, or AI prompt engineer/data labeling job posted recently.
    Format your response strictly as a JSON object with keys:
    "role_title", "company", "salary", "location", "sector", "requirements"
    - "salary": specify real salary range if found, or "Competitive"
    - "requirements": a 2-3 sentence summary of requirements and criteria.
    Do not include markdown code block ticks.
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_job,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        text = response.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        data["job_role"] = json.loads(text)
    except Exception as e:
        print(f"Error fetching live job role: {e}")

    # 4. Fetch Event
    print("Fetching live Event data...")
    prompt_event = """
    Search for a real, upcoming finance, tech, startup, or family office conference or networking event (e.g. in Lagos, London, or New York) scheduled for 2026.
    Format your response strictly as a JSON object with keys:
    "event_title", "organizer", "location", "venue", "description"
    - "description": 2-3 sentences overview of who should attend and what will be discussed.
    Do not include markdown code block ticks.
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_event,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        text = response.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        data["event_data"] = json.loads(text)
    except Exception as e:
        print(f"Error fetching live event: {e}")

    # 5. Fetch Lifestyle Item
    print("Fetching live Lifestyle Item data...")
    prompt_lifestyle = """
    Search for a real luxury item released or popular recently (e.g. a specific high-end watch model like Rolex GMT-Master II, Audemars Piguet Royal Oak, or a luxury sports car like Porsche 911 GT3).
    Format your response strictly as a JSON object with keys:
    "price", "category", "item_name", "maker", "model", "spec_val_1", "spec_val_2", "description"
    - "spec_val_1": e.g. dial color or engine size/horsepower
    - "spec_val_2": e.g. case material or acceleration/top speed
    - "description": 2-3 sentences highlighting its luxury appeal.
    Do not include markdown code block ticks.
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_lifestyle,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        text = response.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        data["lifestyle_item"] = json.loads(text)
    except Exception as e:
        print(f"Error fetching live lifestyle item: {e}")

    # 6. Fetch Billionaire Spotlight
    print("Fetching live Billionaire Spotlight data...")
    prompt_spotlight = """
    Search for a famous tech or finance billionaire (e.g. Warren Buffett, Elon Musk, Aliko Dangote, Bernard Arnault, Jeff Bezos).
    Find their details and a famous quote about business, investing, or life.
    Format your response strictly as a JSON object with keys:
    "person_name", "person_title", "net_worth", "source_wealth", "quote"
    - "person_name": e.g. "Aliko Dangote"
    - "person_title": e.g. "Founder, Chairman & CEO of Dangote Group"
    - "net_worth": e.g. "$13.9 Billion"
    - "source_wealth": e.g. "Cement, Sugar, Flour"
    - "quote": A short inspiring quote.
    Do not include markdown code block ticks.
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_spotlight,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        text = response.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        data["spotlight_item"] = json.loads(text)
    except Exception as e:
        print(f"Error fetching live spotlight item: {e}")

    return data

def main():
    recipient = "richmondeke@gmail.com"
    if len(sys.argv) > 1 and "@" in sys.argv[1]:
        recipient = sys.argv[1]
        
    print(f"Target design showcase recipient: {recipient}")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    images_dir = os.path.join(project_root, "NewsReport", "images")
    os.makedirs(images_dir, exist_ok=True)
    
    # 1. Fetch live data
    live_data = fetch_live_data_via_gemini() or {}
    
    # 2. Build Daily Deal Card data
    daily_deal = {
        "startup": "Shield AI",
        "amount": "$200 Million",
        "stage": "Series F",
        "industry": "Defense Tech",
        "investors": "U.S. Innovative Technology Fund, Riot Ventures",
        "summary": "Shield AI builds autonomous pilot software for military aircraft. Their technology enables jet fighters and quadcopters to navigate and complete tactical missions without GPS or communications links."
    }
    if "daily_deal" in live_data:
        daily_deal.update(live_data["daily_deal"])
    
    # Query Pinterest for daily deal image using the actual startup name or industry
    daily_deal_query = f"{daily_deal['startup']} logo startup"
    daily_deal_img = get_pinterest_image_or_fallback(
        daily_deal_query,
        "https://images.unsplash.com/photo-1508614589041-895b88991e3e?auto=format&fit=crop&w=800&q=80"
    )
    daily_deal["deal_image"] = daily_deal_img
    
    # 3. Build Breaking News Card data
    breaking_deal = {
        "startup": "Retool Corp",
        "amount": "$45 Million",
        "stage": "Series C",
        "industry": "Developer Tools",
        "investors": "Sequoia Capital, Y Combinator, Patrick Collison",
        "summary": "Retool is a low-code platform that lets developers construct internal database dashboards and client administration tools up to 10x faster."
    }
    if "breaking_deal" in live_data:
        breaking_deal.update(live_data["breaking_deal"])
        
    breaking_deal_query = f"{breaking_deal['startup']} startup technology"
    breaking_deal_img = get_pinterest_image_or_fallback(
        breaking_deal_query,
        "https://images.unsplash.com/photo-1555066931-4365d14bab8c?auto=format&fit=crop&w=800&q=80"
    )
    breaking_deal["deal_image"] = breaking_deal_img
    
    # 4. Build Jobs Card data
    job_role = {
        "role_title": "Lead Venture Analyst",
        "company": "The Investor Ventures",
        "salary": "$140,000 - $180,000",
        "location": "Lagos, Nigeria (Hybrid)",
        "sector": "Private Capital",
        "requirements": "Looking for a high-performing VC analyst with 3+ years experience evaluating African tech series A deals. Must be proficient in financial modeling and cap table audit workflows."
    }
    if "job_role" in live_data:
        job_role.update(live_data["job_role"])
        
    job_query = f"{job_role['company']} office workspace"
    job_workplace_img = get_pinterest_image_or_fallback(
        job_query,
        "https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=800&q=80"
    )
    job_role["job_image"] = job_workplace_img
    
    # 5. Build Events Card data
    event_data = {
        "event_title": "Family Office Private Dinner",
        "organizer": "The Investor Board",
        "location": "Victoria Island, Lagos",
        "venue": "The Capital Club Lounge",
        "description": "An invite-only private dining experience connecting Nigerian family office managers, HNWI allocators, and top venture fund GPs to discuss stealth private capital deals."
    }
    if "event_data" in live_data:
        event_data.update(live_data["event_data"])
        
    # 6. Build Lifestyle Card data
    lifestyle_item = {
        "price": "$380,000",
        "category": "Horology",
        "item_name": "Cosmograph Daytona Platinum",
        "maker": "Rolex",
        "model": "Ref. 126506-0001",
        "spec_val_1": "Ice Blue Dial",
        "spec_val_2": "Chestnut Brown Ceramic",
        "description": "The Rolex Cosmograph Daytona in 950 platinum features an ice blue dial and a chestnut brown Cerachrom bezel. It is equipped with the calibre 4131 chronograph movement and features a transparent sapphire case back."
    }
    if "lifestyle_item" in live_data:
        lifestyle_item.update(live_data["lifestyle_item"])
        
    lifestyle_query = f"{lifestyle_item['maker']} {lifestyle_item['item_name']} aesthetic"
    lifestyle_watch_img = get_pinterest_image_or_fallback(
        lifestyle_query,
        "https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=800&q=80"
    )
    lifestyle_item["item_image"] = lifestyle_watch_img
    
    # 7. Build Billionaire Spotlight & Quote Card data
    spotlight_item = {
        "person_name": "Aliko Dangote",
        "person_title": "Founder, Chairman & CEO of Dangote Group",
        "net_worth": "$13.9 Billion",
        "source_wealth": "Cement, Sugar, Flour, Oil",
        "quote": "If you don't have ambition, you shouldn't be alive. Nothing is going to be handed to you on a silver platter."
    }
    if "spotlight_item" in live_data:
        spotlight_item.update(live_data["spotlight_item"])
        
    portrait_url = get_wikipedia_portrait(spotlight_item["person_name"])
    if not portrait_url:
        portrait_url = "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=800&q=80"
    spotlight_item["portrait_image"] = portrait_url
    
    # Render & Send Daily Deal Card
    daily_img = os.path.join(images_dir, "showcase_daily_deal.jpg")
    if render_template_to_image(daily_deal, daily_img, "newscard.html"):
        send_design_email("🎨 [DESIGN SHOWCASE] Daily Deal Newscard Layout", "Daily Newscard", daily_img, recipient)
        
    # Render & Send Breaking News Card
    breaking_img = os.path.join(images_dir, "showcase_breaking.jpg")
    if render_template_to_image(breaking_deal, breaking_img, "breaking_newscard.html"):
        send_design_email("🚨 [DESIGN SHOWCASE] Breaking News Alert Layout", "Breaking News Card", breaking_img, recipient)
        
    # Render & Send Jobs Card
    jobs_img = os.path.join(images_dir, "showcase_jobs.jpg")
    if render_template_to_image(job_role, jobs_img, "jobs_carousel.html"):
        send_design_email("💼 [DESIGN SHOWCASE] Featured Jobs Layout", "Jobs Card", jobs_img, recipient)
        
    # Render & Send Events Card
    events_img = os.path.join(images_dir, "showcase_events.jpg")
    if render_template_to_image(event_data, events_img, "events_carousel.html"):
        send_design_email("🎟️ [DESIGN SHOWCASE] Capital Event Invitation Layout", "Events Card", events_img, recipient)
        
    # Render & Send Lifestyle Card
    lifestyle_img = os.path.join(images_dir, "showcase_lifestyle.jpg")
    if render_template_to_image(lifestyle_item, lifestyle_img, "lifestyle_newscard.html"):
        send_design_email("💎 [DESIGN SHOWCASE] Luxury Lifestyle Segment Layout", "Lifestyle Card", lifestyle_img, recipient)
        
    # Render & Send Spotlight Card
    spotlight_img = os.path.join(images_dir, "showcase_spotlight.jpg")
    if render_template_to_image(spotlight_item, spotlight_img, "spotlight_card.html"):
        send_design_email("🏢 [DESIGN SHOWCASE] Billionaire Spotlight & Quote Layout", "Spotlight Card", spotlight_img, recipient)

if __name__ == "__main__":
    # Load .env if present
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    name, value = line.strip().split("=", 1)
                    os.environ[name] = value
                    
    main()
