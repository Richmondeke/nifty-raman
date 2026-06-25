#!/usr/bin/env python3
import os
import re
import sys
import json
import time
import glob
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime, timedelta
from urllib.parse import urljoin

# Import feedparser and bs4 if available
try:
    import feedparser
    from bs4 import BeautifulSoup
except ImportError:
    print("Warning: feedparser and beautifulsoup4 are required.")

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("Warning: gspread and google-auth are required.")

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Warning: google-genai is required. Please run pip install google-genai.")

def fetch_rss_deals(feed_url, source_name):
    print(f"Fetching {source_name} deals...")
    try:
        import feedparser
        from bs4 import BeautifulSoup
    except ImportError:
        return []
    feed = feedparser.parse(feed_url)
    articles = []
    cutoff = datetime.now() - timedelta(hours=36)
    
    for entry in feed.entries:
        try:
            published_dt = datetime(*entry.published_parsed[:6])
            if published_dt < cutoff:
                continue
            
            soup = BeautifulSoup(entry.summary, "html.parser")
            desc = soup.get_text()
            
            articles.append({
                "title": entry.title,
                "link": entry.link,
                "description": desc,
                "source": source_name
            })
        except Exception as e:
            print(f"Error parsing {source_name} entry: {e}")
            
    print(f"Retrieved {len(articles)} recent articles from {source_name}.")
    return articles

def fetch_hn_deals():
    print("Fetching Hacker News stories containing funding terms...")
    twenty_four_hours_ago = int(time.time()) - 24 * 3600
    query_terms = ["raises", "funding", "seed round", "Series A", "Series B", "Series C", "Series D", "venture capital", "valuation"]
    
    articles = []
    seen_ids = set()
    
    for term in query_terms:
        url = f"https://hn.algolia.com/api/v1/search_by_date?query={term}&tags=story&numericFilters=created_at_i>{twenty_four_hours_ago}"
        try:
            res = requests.get(url, timeout=15)
            if res.status_code != 200:
                continue
            
            hits = res.json().get("hits", [])
            for hit in hits:
                story_id = hit.get("objectID")
                if story_id in seen_ids:
                    continue
                seen_ids.add(story_id)
                
                title = hit.get("title")
                link = hit.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
                
                articles.append({
                    "title": title,
                    "link": link,
                    "description": f"Hacker News discussion: {title}",
                    "source": "Hacker News"
                })
        except Exception as e:
            print(f"Error fetching HN query '{term}': {e}")
            
    print(f"Retrieved {len(articles)} stories from Hacker News.")
    return articles

def parse_with_gemini(articles):
    print("Using Gemini API to extract and structure fundraising deals...")
    
    input_text = json.dumps(articles, indent=2)
    
    prompt = f"""
    You are an expert venture capital researcher. Analyze the following articles and extract only actual startup fundraising announcements or venture capital deals. Ignore general tech tutorials, product updates, M&As (unless major), or opinion essays.
    
    For each valid deal, extract:
    1. Startup Name
    2. Deal details (amount and stage, e.g. "$15 Million Series A", "$5 Million Seed", "undisclosed Series B")
    3. Clean Amount Raised (strictly formatted like "$110 Million", "$50 Billion", "$500 Thousand". If undisclosed, use "Undisclosed")
    4. Clean Stage (keep it extremely simple, e.g. "Preseed", "Seed", "Series A", "Series B", "Series C", "Series D", "Growth", "M&A", "Debt", "Undisclosed". Do not add extra words)
    5. Summary (2-4 sentences explaining what the company does and why it is notable)
    6. Lead/Participating Investors (If the article says "undisclosed", "unknown", or has missing investor details, you MUST use the GOOGLE SEARCH tool to research and find the actual lead/participating investors for this specific funding round. If they are still not found after searching, write "Undisclosed")
    7. Source Domain (e.g. "TechCrunch" or "Hacker News")
    8. URL
    9. Keywords (3-4 relevant tags, e.g. "healthtech", "AI-infrastructure", "saas")
    10. Quality Score (1 to 5, where 5 is a massive/groundbreaking deal, 3 is standard, 1 is minor)
    11. Is African (true if the startup is based in Africa or has African founders, false otherwise)
    
    Output the results strictly as a JSON array containing objects with these exact keys:
    "startup", "deal_details", "amount", "stage", "summary", "investors", "source", "url", "keywords", "score", "is_african"
    
    Articles Data:
    {input_text}
    """
    
    # Prepare a list of Gemini API keys: primary from env or default, plus any fallbacks from GEMINI_FALLBACK_KEYS (comma-separated)
    primary_key = os.getenv("GEMINI_API_KEY") or "AIzaSyAJ8_n_DgKAFOvBPmmBFJj3MF2lux48TFk"
    os.environ["GEMINI_API_KEY"] = primary_key  # Ensure primary is set for downstream uses
    # Determine fallback Gemini API keys (additional keys)
    extra = os.getenv("GEMINI_FALLBACK_KEYS")
    if extra:
        fallback_keys = [k.strip() for k in extra.split(",") if k.strip()]
    else:
        # Hardcoded fallback keys as per user-provided list
        fallback_keys = [
            "AIzaSyDG41fW-E5h3QnCPhFYaEXXwAHwCW5DnnA",
            "AIzaSyB87I6-g2VAbc_upqCuqNXOu-b9ilksTC4",
            "AIzaSyD_Hxblh7EwQembogaG3sdJuJ4L9cVTgfE",
            "AIzaSyByFGLPZC7ZLQnVImgUZC9TKD00My-VUyQ"
        ]
    all_keys = [primary_key] + fallback_keys

    client = None
    response = None
    for key in all_keys:
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )
            # If we get a response, break out of the loop
            break
        except Exception as e:
            print(f"Gemini API call failed with key {key[:5]}...: {e}")
            # Continue to next key
            continue
    if not response:
        print("All Gemini API keys failed. Returning empty result set.")
        return []

    # Parse the JSON response robustly
    text = response.text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Attempt to parse the JSON, with robust fallback on failure
    def try_parse_json(raw_text):
        """Try to parse JSON, with regex extraction fallback."""
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            pass
        # Fallback: try to extract just the JSON array via regex
        json_match = re.search(r"\[\s*\{.*\}\s*\]", raw_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        return None

    deals = try_parse_json(text)

    # If parsing failed, retry the Gemini call once more with the next available key
    if deals is None:
        print("JSON parse failed on first attempt. Retrying Gemini call...")
        retry_response = None
        for key in all_keys:
            try:
                retry_client = genai.Client(api_key=key)
                retry_response = retry_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        tools=[types.Tool(google_search=types.GoogleSearch())]
                    )
                )
                break
            except Exception as e:
                print(f"Retry Gemini call failed with key {key[:5]}...: {e}")
                continue
        if retry_response:
            retry_text = retry_response.text.strip()
            if retry_text.startswith("```json"):
                retry_text = retry_text[7:]
            elif retry_text.startswith("```"):
                retry_text = retry_text[3:]
            if retry_text.endswith("```"):
                retry_text = retry_text[:-3]
            retry_text = retry_text.strip()
            deals = try_parse_json(retry_text)

    if deals is None:
        print("Failed to parse Gemini response as JSON after retries. Returning empty.")
        return []

    print(f"Gemini successfully extracted {len(deals)} deals.")
    return deals

def render_templated_card(deal, api_key, template_id):
    """
    Renders an image card for a deal using Templated.io API
    """
    print(f"Rendering Templated.io card for {deal['startup']}...")
    url = "https://api.templated.io/v1/render"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Extract first keyword for Industry
    industry = "Startup"
    if deal.get("keywords"):
        if isinstance(deal["keywords"], list) and len(deal["keywords"]) > 0:
            industry = deal["keywords"][0].title()
        elif isinstance(deal["keywords"], str):
            kws = [k.strip() for k in re.split(r'[\s,]+', deal["keywords"]) if k.strip()]
            if kws:
                industry = kws[0].title()

    # Format amount strictly (e.g. $110 Million or $50 Billion)
    amount = deal.get("amount", "Undisclosed").strip()
    match = re.search(r'\$\s*(\d+(?:\.\d+)?)\s*([MmbB](?:illion|illion)?|[Kk](?:housand)?)', amount, re.IGNORECASE)
    if match:
        num = match.group(1)
        if num.endswith('.0'):
            num = num[:-2]
        unit = match.group(2).lower()
        if unit.startswith('m'):
            amount = f"${num} Million"
        elif unit.startswith('b'):
            amount = f"${num} Billion"
        elif unit.startswith('k'):
            amount = f"${num} Thousand"
    else:
        amount = re.sub(r'\bmillion\b', 'Million', amount, flags=re.IGNORECASE)
        amount = re.sub(r'\bbillion\b', 'Billion', amount, flags=re.IGNORECASE)
        amount = re.sub(r'\bthousand\b', 'Thousand', amount, flags=re.IGNORECASE)

    # Keep stage extremely clean and simple
    stage = deal.get("stage", "Seed").strip().title()
    stage_map = {
        "Pre-Seed": "Preseed",
        "Pre Seed": "Preseed",
        "Preseed": "Preseed",
        "Seed": "Seed",
        "Series A": "Series A",
        "Series B": "Series B",
        "Series C": "Series C",
        "Series D": "Series D",
        "Growth": "Growth",
        "M&A": "M&A",
        "M&a": "M&A",
        "Debt": "Debt",
        "Undisclosed": "Undisclosed"
    }
    stage = stage_map.get(stage, stage)

    data = {
        "template": template_id,
        "format": "jpg",
        "layers": {
            "company": {"text": deal["startup"]},
            "Amount Raised": {"text": amount},
            "Description": {"text": deal["summary"]},
            "Industry": {"text": industry},
            "text-1-copy-copy-copy-copy-copy": {"text": stage}
        }
    }
    try:
        res = requests.post(url, json=data, headers=headers, timeout=20)
        if res.status_code == 200:
            res_json = res.json()
            image_url = res_json.get("render_url") or res_json.get("url")
            print(f"Successfully rendered card: {image_url}")
            return image_url
        else:
            print(f"Templated.io error: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Failed to connect to Templated.io: {e}")
    return None

def render_creatomate_card(deal, api_key, template_id):
    """
    Renders a video or image card for a deal using Creatomate API
    """
    print(f"Rendering Creatomate card for {deal['startup']}...")
    url = "https://api.creatomate.com/v1/renders"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    # These modification keys can be configured in your Creatomate template
    data = {
        "template_id": template_id,
        "modifications": {
            "Startup-Name": deal["startup"],
            "Deal-Details": deal["deal_details"],
            "Summary": deal["summary"],
            "Investors": f"Investors: {deal['investors']}"
        }
    }
    try:
        res = requests.post(url, json=data, headers=headers, timeout=20)
        if res.status_code == 200:
            res_json = res.json()
            # Creatomate can return a list or object depending on configuration
            render_url = res_json[0].get("url") if isinstance(res_json, list) else res_json.get("url")
            print(f"Successfully rendered Creatomate card: {render_url}")
            return render_url
        else:
            print(f"Creatomate error: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Failed to connect to Creatomate: {e}")
    return None

def write_markdown_report(deals):
    date_str = datetime.now().strftime("%Y-%m-%d")
    report_dir = "NewsReport"
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f"{date_str}-news-report.md")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Daily News Report ({date_str})\n\n")
        f.write(f"> Curated from TechCrunch and Hacker News. Contains {len(deals)} fundraising deals.\n")
        f.write(f"> Generated automatically via GitHub Actions.\n\n")
        f.write("---\n\n")
        
        for i, deal in enumerate(deals, 1):
            f.write(f"## {i}. {deal['startup']}: {deal['deal_details']}\n\n")
            f.write(f"- **Summary**: {deal['summary']}\n")
            f.write(f"- **Key Points**:\n")
            f.write(f"  1. Investors: {deal['investors']}\n")
            f.write(f"  2. Sector keywords: {', '.join(deal['keywords'] if isinstance(deal['keywords'], list) else [deal['keywords']])}\n")
            f.write(f"- **Source**: [{deal['source']}]({deal['url']})\n")
            
            # Write image link if generated
            if "rendered_image_url" in deal and deal["rendered_image_url"]:
                f.write(f"- **Generated Card**: [View Rendered Image]({deal['rendered_image_url']})\n")
                if "local_image_path" in deal and deal["local_image_path"]:
                    # Relative path from the report file is images/[filename]
                    relative_img_path = os.path.join("images", os.path.basename(deal["local_image_path"]))
                    f.write(f"\n![Visual Card]({relative_img_path})\n\n")
                
            f.write(f"- **Keywords**: {' '.join([f'`{k}`' for k in (deal['keywords'] if isinstance(deal['keywords'], list) else [deal['keywords']])])}\n")
            f.write(f"- **Score**: {'⭐' * int(deal['score'])} ({deal['score']}/5)\n\n")
            f.write("---\n\n")
            
        f.write(f"*Generated by Daily News Report v3.0*\n")
        
    print(f"Markdown report written to {report_path}")
    return report_path

def upload_to_sheets(deals, credentials_json, spreadsheet_name, sheet_name="Fundraising Deals"):
    if not credentials_json:
        print("Warning: GOOGLE_SHEETS_CREDENTIALS environment variable is empty. Skipping Sheets upload.")
        return
        
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    
    try:
        creds_dict = json.loads(credentials_json)
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
        gc = gspread.authorize(credentials)
    except Exception as e:
        print(f"Sheets Auth Error: {e}")
        return

    try:
        sh = gc.open(spreadsheet_name)
    except Exception as e:
        print(f"Sheets Access Error: Spreadsheet '{spreadsheet_name}' not found. {e}")
        return

    try:
        worksheet = sh.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sh.add_worksheet(title=sheet_name, rows="100", cols="9")
        # Added extra column for Rendered Card URL
        headers = ["Date", "Startup", "Deal Details", "Summary", "Source URL", "Keywords", "Score", "Card URL"]
        worksheet.append_row(headers)
        
    existing_urls = set(worksheet.col_values(5)[1:])
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    rows_to_append = []
    for d in deals:
        url = d.get("url", "")
        if url in existing_urls:
            continue
            
        kw_str = ", ".join(d.get("keywords", [])) if isinstance(d.get("keywords"), list) else str(d.get("keywords", ""))
        card_url = d.get("rendered_image_url", "")
        
        rows_to_append.append([
            date_str,
            d.get("startup", ""),
            d.get("deal_details", ""),
            d.get("summary", ""),
            url,
            kw_str,
            d.get("score", ""),
            card_url
        ])
        
    if rows_to_append:
        worksheet.append_rows(rows_to_append)
        print(f"Appended {len(rows_to_append)} rows to Google Sheets.")
    else:
        print("No new deals to write to Google Sheets.")

def download_image(url, save_path):
    try:
        res = requests.get(url, timeout=20)
        if res.status_code == 200:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(res.content)
            print(f"Successfully downloaded and saved card to: {save_path}")
            return True
        else:
            print(f"Failed to download image: {res.status_code}")
    except Exception as e:
        print(f"Error downloading image: {e}")
    return False

def extract_og_image(url):
    """
    Crawls the article URL to extract the og:image or twitter:image thumbnail
    """
    if not url or not url.startswith("http"):
        return None
    print(f"Extracting OG image for: {url}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            # Try og:image
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                full_url = urljoin(url, og_img["content"])
                print(f"Found og:image: {full_url}")
                return full_url
            # Try twitter:image
            tw_img = soup.find("meta", name="twitter:image")
            if tw_img and tw_img.get("content"):
                full_url = urljoin(url, tw_img["content"])
                print(f"Found twitter:image: {full_url}")
                return full_url
            # Try standard image as fallback
            for img in soup.find_all("img"):
                src = img.get("src")
                if src and ("featured" in src or "article" in src or "upload" in src) and not src.endswith(".gif"):
                    full_url = urljoin(url, src)
                    print(f"Found fallback image: {full_url}")
                    return full_url
    except Exception as e:
        print(f"Error extracting OG image from {url}: {e}")
    return None

def generate_newsletter_html(deals, gemini_key, investor_spotlight=None):
    """
    Generates a premium, investor-centric newsletter HTML body using Gemini API.
    Highlights weekly HNWI / Family Office events and incorporates article image URLs.
    Uses a relatable, simple writing style and embeds the logo.
    """
    print("Generating premium newsletter HTML via Gemini...")
    client = genai.Client(api_key=gemini_key)
    date_str = datetime.now().strftime("%B %d, %Y")
    
    # Structure deals data cleanly for the prompt
    deals_data = []
    for d in deals:
        deals_data.append({
            "startup": d.get("startup"),
            "deal_details": d.get("deal_details"),
            "summary": d.get("summary"),
            "investors": d.get("investors"),
            "url": d.get("url"),
            "article_image_url": d.get("article_image_url"),
            "keywords": d.get("keywords"),
            "score": d.get("score"),
            "is_african": d.get("is_african")
        })
        
    prompt = f"""
    You are a friendly, down-to-earth financial editor for "The Investor", a daily venture briefing sent to HNWIs, Family Offices, and Venture Capitalists.
    
    Generate the HTML content for today's newsletter ({date_str}).
    Use inline CSS inside the HTML style attributes to ensure it renders beautifully in Gmail and other email clients.
    
    The newsletter must follow these design guidelines:
                - Palette: Deep rich blues (#0F172A), luxurious warm gold/amber accents (#D97706 or #B45309), slate gray for text (#475569), clean ivory/white backgrounds (#FFFFFF). Header background is black (#000000) with white text. Investor spotlight uses grass‑green accent (#7ED957).
        - Typography: Serif headers (e.g. "Georgia", "Garamond", serif) and body text in "DM Sans" (fallback to "Inter", "Helvetica Neue", Arial, sans-serif).
    
    1. Elegant Header: Embed the logo using <img src="cid:logo_image" alt="The Investor" style="height: 105px; display: block; margin: 0 auto 10px auto; max-width: 250px;">. Display the edition date and a subtitle below it: "Daily private capital & events briefing".
    - Typography: Serif headers (e.g. "Georgia", "Garamond", serif) and clean, easy-to-read sans-serif body text (e.g. "Inter", "Helvetica Neue", Arial, sans-serif).
    - Responsive layout with a max-width of 600px, centered, with comfortable padding (e.g., 20px-30px), soft borders, and premium-looking cards.
    
    The content structure must include:
    1. Elegant Header: Embed the logo using <img src="cid:logo_image" alt="The Investor" style="height: 50px; display: block; margin: 0 auto 10px auto; max-width: 250px;">. Display the edition date and a subtitle below it: "Daily private capital & events briefing".
    2. Global Editorial Intro: Write a friendly, relatable greeting from Richmond ("Richmond from The Investor"). Explain what is happening in the global venture market today in plain English.
    3. Top Deal of the Day:
       - Insert the visual card image with `src="cid:top_deal_image"` to display it inline.
       - Provide a readable, relatable write-up of this top deal below the image.
    4. Top Investor Spotlight:
       - Embed the portrait using <img src="cid:investor_image" alt="{investor_spotlight.get('name') if investor_spotlight else ''}" style="height:120px; display:block; margin:0 auto 10px auto; border-radius:8px;">
       - <p style="font-family:'DM Sans',Arial,sans-serif; color:#475569; text-align:center; margin:0 0 15px 0;">{investor_spotlight.get('summary') if investor_spotlight else ''}</p>
    5. 🚀 Top Global Deals:
       - Format the global deals (those with is_african = false or missing) from the following data: {json.dumps(deals_data, indent=2)}
       - For each deal, present a simple summary, investors, and sector/keywords.
       - If a deal has a non-null/valid 'article_image_url', embed that image inside the deal card/section with style: `width: 100%; max-height: 250px; object-fit: cover; border-radius: 8px; margin: 12px 0;`.
    6. 🌍 African & Nigerian Spotlight:
       - Start this section with a warm, friendly intro from Kamsy ("Kamsy from The Investor"). Have him share a brief thought on today's African tech news or ecosystem growth.
       - Format the African deals (those with is_african = true) from the same data array.
       - Render them distinctly in their own styled section.
       - Follow the same card format rules as global deals.
    7. Events of the Week for HNWIs & Family Offices:
       - Create an exclusive events section highlighting 2-3 high-value events of the week.
    8. Premium Footer: Standard newsletter footer with branding, disclaimers, and subscription terms.
    
    Return ONLY the raw HTML code. Do not include markdown code block backticks.
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        html_code = response.text.strip()
        # Clean potential markdown output
        if html_code.startswith("```html"):
            html_code = html_code[7:]
        elif html_code.startswith("```"):
            html_code = html_code[3:]
        if html_code.endswith("```"):
            html_code = html_code[:-3]
        return html_code.strip()
    except Exception as e:
        print(f"Error generating newsletter HTML via Gemini: {e}")
        return None

def send_gmail(deals, local_image_path=None, investor_image_path=None, investor_spotlight=None, test_recipient=None):
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    if not gmail_user or not gmail_password:
        print("Warning: GMAIL_USER or GMAIL_APP_PASSWORD not set. Skipping Gmail notification.")
        return
        
    if test_recipient:
        recipients = [test_recipient]
    else:
        recipients = ["richmondeke@gmail.com", "kamsyosakwe@gmail.com", "masiyerdakol@gmail.com", "troyhodinni@gmail.com"]
    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"The Investor's Daily Fundraising Report - {date_str}"
    
    html_content = None
    if gemini_key:
        html_content = generate_newsletter_html(deals, gemini_key, investor_spotlight)
        
    if not html_content:
        # Fallback ...
        html_parts = ["<html>", "<body style='font-family: Arial, sans-serif; color: #333; line-height: 1.6;'>", "<p>Hi Investor,</p>"]
        if local_image_path and os.path.exists(local_image_path):
            html_parts.append("<img src='cid:top_deal_image' style='max-width: 600px;'>")
        html_content = "\n".join(html_parts) + "</body></html>"
    
    logo_path = os.path.join("assets", "TheInvestor.png")
    
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(gmail_user, gmail_password)
        
        for recipient in recipients:
            msg = MIMEMultipart('related')
            msg['Subject'] = subject
            msg['From'] = f"The Investor <{gmail_user}>"
            msg['To'] = recipient
            
            msg_html = MIMEText(html_content, 'html')
            msg.attach(msg_html)
            
            if os.path.exists(logo_path):
                with open(logo_path, 'rb') as f:
                    msg_logo = MIMEImage(f.read())
                    msg_logo.add_header('Content-ID', '<logo_image>')
                    msg.attach(msg_logo)
            
            if local_image_path and os.path.exists(local_image_path):
                with open(local_image_path, 'rb') as f:
                    msg_img = MIMEImage(f.read())
                    msg_img.add_header('Content-ID', '<top_deal_image>')
                    msg.attach(msg_img)

            if investor_image_path and os.path.exists(investor_image_path):
                try:
                    with open(investor_image_path, 'rb') as f:
                        msg_inv = MIMEImage(f.read())
                        msg_inv.add_header('Content-ID', '<investor_image>')
                        msg.attach(msg_inv)
                except Exception as e:
                    print(f"Error attaching investor image for {recipient}: {e}")
            
            server.sendmail(gmail_user, [recipient], msg.as_string())
            
        server.close()
    except Exception as e:
        print(f"Error sending emails via Gmail: {e}")

if __name__ == "__main__":
    # Load environment variables
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    env_path = os.path.join(project_root, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    os.environ[k.strip()] = v.strip().strip("'\"")

    test_recipient = None
    use_mock = False
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if "@" in arg:
                test_recipient = arg
                print(f"Test mode active. Test recipient set to: {test_recipient}")
            elif arg in ("--mock", "-m"):
                use_mock = True
                print("Mock mode active. Bypassing live feeds and Gemini extraction.")

    spreadsheet = os.environ.get("SPREADSHEET_NAME")
    templated_key = os.environ.get("TEMPLATED_API_KEY")
    templated_id = os.environ.get("TEMPLATED_TEMPLATE_ID")
    creatomate_key = os.environ.get("CREATOMATE_API_KEY")
    creatomate_id = os.environ.get("CREATOMATE_TEMPLATE_ID")
        
    deals = []
    if use_mock:
        deals = [{
            "startup": "The Investor",
            "deal_details": "raised $10 Million Series A",
            "amount": "$10 Million",
            "stage": "Series A",
            "keywords": ["Fintech", "Media"],
            "investors": "Vanguard, Tiger Global",
            "summary": "The Investor is a premium capital briefing platform that delivers curated venture funding news and family office insights to HNWI readers.",
            "source": "TechCrunch",
            "url": "https://theinvestor.news",
            "is_african": False,
            "score": 5
        }]
    else:
        articles = []
        articles.extend(fetch_rss_deals("https://techcrunch.com/category/venture/feed/", "TechCrunch"))
        articles.extend(fetch_rss_deals("https://techcabal.com/feed/", "TechCabal"))
        articles.extend(fetch_rss_deals("https://disrupt-africa.com/feed/", "Disrupt Africa"))
        articles.extend(fetch_hn_deals())
        
        if not articles:
            sys.exit(0)
            
        deals = parse_with_gemini(articles)
        if deals:
            for d in deals:
                d["article_image_url"] = extract_og_image(d.get("url"))

    if deals:

        try:
            deals.sort(key=lambda d: int(d.get("score", 0)), reverse=True)
        except Exception as e:
            print(f"Error sorting deals: {e}")

        # Determine top investor
        def select_top_investor(deals):
            investor_counts = {}
            for d in deals:
                invs = d.get("investors", "")
                for inv in [i.strip() for i in str(invs).split(",") if i.strip()]:
                    investor_counts[inv] = investor_counts.get(inv, 0) + 1
            if not investor_counts:
                return None
            return max(investor_counts, key=investor_counts.get)

        def generate_investor_summary(name, gemini_key):
            if not name: return ""
            client = genai.Client(api_key=gemini_key)
            prompt = f"You are a financial editor. Write a brief 2-3 sentence paragraph about the investor {name}, mentioning why they matter to HNWI readers."
            try:
                response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                return response.text.strip()
            except: return ""

        top_investor_name = select_top_investor(deals)
        top_investor_summary = generate_investor_summary(top_investor_name, os.environ.get("GEMINI_API_KEY"))
        investor_spotlight = {"name": top_investor_name, "summary": top_investor_summary, "cid": "investor_image"}
        
        # Image logic (Assumes local storage at standard path)
        investor_img_path = os.path.join("NewsReport", "images", "investor_portrait.jpg")

        top_deal = deals[0]
        date_str = datetime.now().strftime("%Y-%m-%d")
        image_filename = f"{date_str}-top-deal.jpg"
        local_img_path = os.path.join("NewsReport", "images", image_filename)
        
        # Try local Playwright newscard generation first
        render_success = False
        try:
            try:
                from scripts.render_newscard import render_newscard
            except ImportError:
                sys.path.append(os.path.dirname(os.path.abspath(__file__)))
                from render_newscard import render_newscard
                
            render_success = render_newscard(top_deal, local_img_path)
            if render_success:
                top_deal["local_image_path"] = local_img_path
                print(f"Successfully generated local HTML newscard for {top_deal['startup']}")
        except Exception as e:
            print(f"Failed to generate local HTML newscard: {e}. Falling back to API card generation.")
            
        if not render_success:
            rendered_url = None
            if templated_key and templated_id:
                rendered_url = render_templated_card(top_deal, templated_key, templated_id)
            elif creatomate_key and creatomate_id:
                rendered_url = render_creatomate_card(top_deal, creatomate_key, creatomate_id)
            
            if rendered_url:
                top_deal["rendered_image_url"] = rendered_url
                print(f"Top deal visual card generated successfully via API for: {top_deal['startup']}")
                if download_image(rendered_url, local_img_path):
                    top_deal["local_image_path"] = local_img_path
                
        write_markdown_report(deals)
        
        # Send notifications via Gmail
        send_gmail(deals, local_img_path, investor_img_path, investor_spotlight, test_recipient)
        
        if spreadsheet:
            sheets_creds = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
            upload_to_sheets(deals, sheets_creds, spreadsheet)
    if not deals:
        print("No deals found after LLM extraction.")
        # Create a retry flag for later retry workflow
        retry_flag = os.path.join(os.path.dirname(__file__), "..", "..", ".retry_needed")
        try:
            with open(retry_flag, "w") as f:
                f.write(str(datetime.utcnow()))
        except Exception as e:
            print(f"Failed to write retry flag: {e}")
        # Exit with non-zero to mark the GitHub Action as failed
        sys.exit(1)

