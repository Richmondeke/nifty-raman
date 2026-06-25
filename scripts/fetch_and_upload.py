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
    cutoff = datetime.now() - timedelta(days=7)
    
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

def format_deal_list(deals_list):
    if not deals_list:
        return '<p style="font-family: \'Satoshi\', Arial, sans-serif; font-size: 13px; color: #94A3B8; font-style: italic;">No other major rounds reported today.</p>'
    
    html_blocks = []
    for d in deals_list:
        keywords = d.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        
        keywords_tags = "".join([
            f'<span style="background-color: #7ED957; color: #000000; font-size: 11px; padding: 2px 8px; border: 1px solid #000000; margin-right: 5px; font-weight: 700; display: inline-block; margin-bottom: 4px;">{k}</span>' 
            for k in keywords if k
        ])
        
        html_blocks.append(f"""
        <div style="border: 2px solid #000000; padding: 15px; margin-bottom: 15px; background-color: #FFFFFF; box-shadow: 4px 4px 0px #000000;">
          <h4 style="font-family: 'Satoshi', Arial, sans-serif; font-size: 16px; color: #000000; margin: 0 0 5px 0; font-weight: 900; text-transform: uppercase; letter-spacing: 0.5px;">
            {d.get('startup')} — <span style="color: #B45309;">{d.get('amount')} ({d.get('stage')})</span>
          </h4>
          <p style="font-family: 'Satoshi', Arial, sans-serif; font-size: 14px; color: #000000; margin: 0 0 10px 0; line-height: 1.5; font-weight: 500;">
            {d.get('summary')}
          </p>
          <p style="font-family: 'Satoshi', Arial, sans-serif; font-size: 13px; color: #000000; margin: 0 0 10px 0; font-weight: 700;">
            Investors: {d.get('investors')}
          </p>
          <div style="margin-top: 5px;">
            {keywords_tags}
          </div>
        </div>
        """)
    return "\n".join(html_blocks)

def generate_newsletter_html(deals, gemini_key, investor_spotlight=None):
    """
    Generates a premium, uniform, investor-centric newsletter HTML body.
    Uses Gemini to write the editorial copy (Richmond's greeting and Kamsy's African intro)
    and structures them into a standard HTML template.
    """
    print("Generating uniform newsletter HTML using standard template...")
    
    # Load the email template
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    template_path = os.path.join(project_root, "templates", "newsletter_email.html")
    
    if not os.path.exists(template_path):
        print(f"Error: Newsletter template not found at {template_path}. Returning empty.")
        return None
        
    with open(template_path, "r", encoding="utf-8") as f:
        template_content = f.read()
        
    # Generate the copywriting sections (intros and events) using Gemini
    client = genai.Client(api_key=gemini_key)
    date_str = datetime.now().strftime("%B %d, %Y")
    
    deals_summary = []
    for d in deals:
        deals_summary.append(f"- {d.get('startup')} ({d.get('amount')}, {d.get('stage')}): {d.get('summary')}")
    deals_text = "\n".join(deals_summary)
    
    prompt = f"""
    You are the writing assistant for "The Investor" newsletter. Based on today's venture capital deals:
    {deals_text}
    
    Generate three copywriting elements as JSON. Output exactly a JSON object (no markdown backticks, no comments) with these keys:
    1. "editorial_intro": A friendly, high-quality, professional yet down-to-earth greeting from Richmond ("Richmond from The Investor") to our HNWI/Family Office readers. Summarize the major trends of today's venture capital activities in 2 paragraphs. Do not use HTML tags in this text except standard paragraph tags (<p>...</p>) if needed.
    2. "african_intro": A warm, insightful 1-paragraph thought from Kamsy ("Kamsy from The Investor") focusing on the African startup and VC landscape today.
    3. "events": A list of 2-3 exclusive high-value events of the week for HNWIs and Family Offices (e.g. VIP investor summits, private wealth conferences, venture showcase dinners). For each event, include: "title", "date", and "description".
    
    JSON format:
    {{
      "editorial_intro": "...",
      "african_intro": "...",
      "events": [
        {{
          "title": "...",
          "date": "...",
          "description": "..."
        }}
      ]
    }}
    """
    
    editorial_intro = "<p>Welcome to today's edition of The Investor briefing. Today we highlight major movements in capital markets, private equity allocations, and notable fundraising rounds.</p>"
    african_intro = "Great momentum is building across the African venture space today."
    events_list = [
        {"title": "HNWI Wealth & Venture Summit", "date": "July 12, 2026", "description": "An exclusive gathering of family offices and venture capitalists discussing private equity allocations."},
        {"title": "African Tech Angel Showcase", "date": "July 15, 2026", "description": "Private virtual pitching session with pre-vetted high-growth startups from Lagos, Nairobi, and Cape Town."}
    ]
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        text = response.text.strip()
        
        # Clean markdown codeblocks
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        data = json.loads(text)
        editorial_intro = data.get("editorial_intro", editorial_intro)
        african_intro = data.get("african_intro", african_intro)
        events_list = data.get("events", events_list)
        print("Gemini successfully generated intros and events copy.")
    except Exception as e:
        print(f"Error calling Gemini or parsing JSON copy: {e}. Using fallback copywriting.")
        
    # Format the sections in Python
    
    # 1. Top deals section (highlight top 3 deals)
    top_deals_html = []
    for idx, deal in enumerate(deals[:3]):
        top_deals_html.append(f"""
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 30px; border: 3px solid #000000; overflow: hidden; background-color: #FFFFFF; box-shadow: 6px 6px 0px #000000;">
          <tr>
            <td align="center">
              <img src="cid:top_deal_image_{idx}" alt="{deal.get('startup')} card" style="width: 100%; max-width: 540px; display: block; border-bottom: 3px solid #000000;" />
            </td>
          </tr>
          <tr>
            <td style="padding: 20px; font-family: 'Satoshi', Arial, sans-serif; font-size: 15px; color: #000000; line-height: 1.6; font-weight: 500;">
              <strong style="color: #000000; font-size: 18px; font-weight: 900; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 5px;">{deal.get('startup')}</strong>
              {deal.get('summary')}
              <br/><span style="font-size: 12px; color: #94A3B8; margin-top: 10px; display: inline-block; font-weight: 700; text-transform: uppercase;">Source: {deal.get('source')}</span>
            </td>
          </tr>
        </table>
        """)
    top_deals_section = "\n".join(top_deals_html)
    
    # 2. Spotlight section
    if investor_spotlight and investor_spotlight.get("name"):
        spotlight_section = f"""
        <tr>
          <td align="left" valign="top" style="padding: 20px 40px 10px 40px; background-color: #FFFFFF; border-top: 3px solid #000000; border-bottom: 3px solid #000000;">
            <h3 style="font-family: 'Satoshi', Arial, sans-serif; font-size: 22px; color: #000000; margin: 0 0 15px 0; font-weight: 900; text-transform: uppercase; letter-spacing: 1px;">
              ✨ Investor Spotlight: {investor_spotlight.get('name')}
            </h3>
            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 15px; border: 2px solid #000000; padding: 20px; background-color: #F8FAFC; box-shadow: 4px 4px 0px #000000;">
              <tr>
                <td valign="top" style="font-family: 'Satoshi', Arial, sans-serif; font-size: 14px; color: #000000; line-height: 1.6; font-weight: 500;">
                  {investor_spotlight.get('summary')}
                </td>
              </tr>
            </table>
          </td>
        </tr>
        """
    else:
        spotlight_section = ""
        
    # 3. Global and African deals lists (skip top 3)
    other_deals = deals[3:] if len(deals) > 3 else []
    global_list = [d for d in other_deals if not d.get("is_african")]
    african_list = [d for d in other_deals if d.get("is_african")]
    
    global_deals_section = format_deal_list(global_list)
    african_deals_section = format_deal_list(african_list)
    
    # 4. Events section
    events_html = []
    for ev in events_list:
        events_html.append(f"""
        <div style="margin-bottom: 20px; border: 2px solid #000000; padding: 20px; background-color: #FFFFFF; box-shadow: 4px 4px 0px #000000;">
          <h4 style="font-family: 'Satoshi', Arial, sans-serif; font-size: 16px; color: #000000; margin: 0 0 5px 0; font-weight: 900; text-transform: uppercase;">
            {ev.get('title')}
          </h4>
          <span style="font-family: 'Satoshi', Arial, sans-serif; font-size: 11px; background-color: #7ED957; color: #000000; border: 1px solid #000000; padding: 2px 8px; font-weight: 900; text-transform: uppercase; display: inline-block; margin-bottom: 10px;">
            {ev.get('date')}
          </span>
          <p style="font-family: 'Satoshi', Arial, sans-serif; font-size: 14px; color: #000000; margin: 0; line-height: 1.5; font-weight: 500;">
            {ev.get('description')}
          </p>
        </div>
        """)
    events_section = "\n".join(events_html)
    
    # Compile the final newsletter HTML
    html_body = template_content
    html_body = html_body.replace("{date}", date_str)
    html_body = html_body.replace("{editorial_intro}", editorial_intro)
    html_body = html_body.replace("{top_deals_section}", top_deals_section)
    html_body = html_body.replace("{spotlight_section}", spotlight_section)
    html_body = html_body.replace("{global_deals_section}", global_deals_section)
    html_body = html_body.replace("{african_intro}", african_intro)
    html_body = html_body.replace("{african_deals_section}", african_deals_section)
    html_body = html_body.replace("{events_section}", events_section)
    
    return html_body

def send_gmail(deals, local_image_paths=None, investor_image_path=None, investor_spotlight=None, test_recipient=None):
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
        if local_image_paths:
            for idx, img_path in enumerate(local_image_paths):
                if img_path and os.path.exists(img_path):
                    html_parts.append(f"<div style='margin-bottom: 30px;'><img src='cid:top_deal_image_{idx}' style='max-width: 600px;'></div>")
        html_content = "\n".join(html_parts) + "</body></html>"
    
    logo_path = os.path.join("assets", "TheInvestor.png")
    
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(gmail_user, gmail_password)
        
        for recipient in recipients:
            # Create top-level mixed container (allows standard downloadable attachments)
            msg = MIMEMultipart('mixed')
            msg['Subject'] = subject
            msg['From'] = f"The Investor <{gmail_user}>"
            msg['To'] = recipient
            
            # Create nested related container (for HTML and inline images)
            msg_related = MIMEMultipart('related')
            msg.attach(msg_related)
            
            # Attach the HTML body to the related container
            msg_html = MIMEText(html_content, 'html')
            msg_related.attach(msg_html)
            
            # Attach the inline logo to the related container
            if os.path.exists(logo_path):
                with open(logo_path, 'rb') as f:
                    msg_logo = MIMEImage(f.read())
                    msg_logo.add_header('Content-ID', '<logo_image>')
                    msg_related.attach(msg_logo)
            
            # Attach deal cards / resolved images
            if local_image_paths:
                for idx, img_path in enumerate(local_image_paths):
                    if img_path and os.path.exists(img_path):
                        with open(img_path, 'rb') as f:
                            img_data = f.read()
                            
                            # Attach inline version to related container
                            msg_img_inline = MIMEImage(img_data)
                            msg_img_inline.add_header('Content-ID', f'<top_deal_image_{idx}>')
                            msg_related.attach(msg_img_inline)
                            
                            # Attach standalone downloadable version to mixed container
                            msg_img_attach = MIMEImage(img_data)
                            msg_img_attach.add_header('Content-Disposition', 'attachment', filename=os.path.basename(img_path))
                            msg.attach(msg_img_attach)

            # Attach investor portrait
            if investor_image_path and os.path.exists(investor_image_path):
                try:
                    with open(investor_image_path, 'rb') as f:
                        inv_data = f.read()
                        
                        # Attach inline version to related container
                        msg_inv_inline = MIMEImage(inv_data)
                        msg_inv_inline.add_header('Content-ID', '<investor_image>')
                        msg_related.attach(msg_inv_inline)
                        
                        # Attach standalone downloadable version to mixed container
                        msg_inv_attach = MIMEImage(inv_data)
                        msg_inv_attach.add_header('Content-Disposition', 'attachment', filename=os.path.basename(investor_image_path))
                        msg.attach(msg_inv_attach)
                except Exception as e:
                    print(f"Error attaching investor image for {recipient}: {e}")
            
            server.sendmail(gmail_user, [recipient], msg.as_string())
            print(f"Successfully sent email to {recipient}")
            
        server.close()
        print("Gmail SMTP server connection closed.")
    except Exception as e:
        print(f"Error sending emails via Gmail: {e}")

def send_whatsapp(deals, test_recipient=None):
    """
    Sends a WhatsApp notification summarizing today's venture report.
    Supports CallMeBot (free, simple) and Twilio (professional).
    """
    phone = os.environ.get("WHATSAPP_PHONE")
    apikey = os.environ.get("WHATSAPP_API_KEY") # CallMeBot API key
    
    twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
    twilio_from = os.environ.get("TWILIO_FROM_NUMBER") # Twilio WhatsApp sender e.g. whatsapp:+14155238886
    
    if not (phone and apikey) and not (twilio_sid and twilio_token and twilio_from and phone):
        print("WhatsApp credentials not fully set. Skipping WhatsApp notification.")
        return
        
    date_str = datetime.now().strftime("%Y-%m-%d")
    message = f"🚀 *The Investor Daily Fundraising Report - {date_str}* is out!\n\n"
    message += f"Total Deals: {len(deals)}\n\n"
    
    if deals:
        message += "*Top Deals Today:*\n"
        for idx, d in enumerate(deals[:3], 1):
            message += f"{idx}. {d.get('startup')} raised {d.get('amount')} ({d.get('stage')})\n"
            
    message += "\n📧 Full newsletter report has been sent to your inbox!"
    
    # 1. Try CallMeBot (Free, HTTP-based API)
    if phone and apikey:
        print("Sending WhatsApp notification via CallMeBot...")
        url = "https://api.callmebot.com/whatsapp.php"
        params = {
            "phone": phone,
            "apikey": apikey,
            "text": message
        }
        try:
            res = requests.get(url, params=params, timeout=15)
            if res.status_code == 200:
                print("WhatsApp notification sent successfully via CallMeBot.")
                return
            else:
                print(f"CallMeBot failed with status {res.status_code}: {res.text}")
        except Exception as e:
            print(f"Error sending WhatsApp via CallMeBot: {e}")
            
    # 2. Try Twilio (Professional API)
    if twilio_sid and twilio_token and twilio_from and phone:
        print("Sending WhatsApp notification via Twilio...")
        to_number = phone if phone.startswith("whatsapp:") else f"whatsapp:{phone}"
        from_number = twilio_from if twilio_from.startswith("whatsapp:") else f"whatsapp:{twilio_from}"
        
        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json"
            auth = (twilio_sid, twilio_token)
            payload = {
                "From": from_number,
                "To": to_number,
                "Body": message
            }
            res = requests.post(url, data=payload, auth=auth, timeout=15)
            if res.status_code in (200, 201):
                print("WhatsApp notification sent successfully via Twilio.")
            else:
                print(f"Twilio WhatsApp failed with status {res.status_code}: {res.text}")
        except Exception as e:
            print(f"Error sending WhatsApp via Twilio: {e}")

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
        deals = [
            {
                "startup": "The Investor",
                "deal_details": "raised $10 Million Series A",
                "amount": "$10 Million",
                "stage": "Series A",
                "keywords": ["Fintech", "Media"],
                "investors": "Vanguard, Tiger Global",
                "summary": "The Investor is a premium capital briefing platform that delivers curated venture funding news and family office insights to HNWI readers.",
                "source": "TechCrunch",
                "url": "#",
                "article_image_url": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?auto=format&fit=crop&w=800&q=80",
                "is_african": False,
                "score": 5
            },
            {
                "startup": "Raman AI",
                "deal_details": "raised $5 Million Seed",
                "amount": "$5 Million",
                "stage": "Seed",
                "keywords": ["AI Infrastructure", "SaaS"],
                "investors": "Y Combinator, Sequoia Capital",
                "summary": "Raman AI builds high-performance agentic pipelines and developer tools designed to streamline corporate workflows and LLM fine-tuning.",
                "source": "TechCrunch",
                "url": "https://techcrunch.com",
                "article_image_url": "https://images.unsplash.com/photo-1498050108023-c5249f4df085?auto=format&fit=crop&w=800&q=80",
                "is_african": False,
                "score": 4
            },
            {
                "startup": "Antigravity Corp",
                "deal_details": "raised $20 Million Series B",
                "amount": "$20 Million",
                "stage": "Series B",
                "keywords": ["Deeptech", "Aerospace"],
                "investors": "Founders Fund, Andreessen Horowitz",
                "summary": "Antigravity Corp is pioneering advanced propulsion systems and orbital logistics platforms to support commercial space missions.",
                "source": "TechCrunch",
                "url": "https://techcrunch.com",
                "article_image_url": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=800&q=80",
                "is_african": False,
                "score": 5
            }
        ]
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

        # Generate newscards for the top deals (up to 3)
        local_image_paths = []
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        try:
            from scripts.render_newscard import render_newscard
        except ImportError:
            sys.path.append(os.path.dirname(os.path.abspath(__file__)))
            from render_newscard import render_newscard

        for idx, deal in enumerate(deals[:3]):
            startup_clean = deal.get("startup", f"deal_{idx}").replace(" ", "_").replace("/", "_")
            image_filename = f"{date_str}-{startup_clean}-card.jpg"
            local_img_path = os.path.join("NewsReport", "images", image_filename)
            
            render_success = False
            try:
                render_success = render_newscard(deal, local_img_path)
                if render_success:
                    deal["local_image_path"] = local_img_path
                    print(f"Successfully generated local HTML newscard for {deal['startup']}")
            except Exception as e:
                print(f"Failed to generate local HTML newscard for {deal.get('startup')}: {e}. Falling back to API card generation.")
                
            if not render_success:
                rendered_url = None
                if templated_key and templated_id:
                    rendered_url = render_templated_card(deal, templated_key, templated_id)
                elif creatomate_key and creatomate_id:
                    rendered_url = render_creatomate_card(deal, creatomate_key, creatomate_id)
                
                if rendered_url:
                    deal["rendered_image_url"] = rendered_url
                    print(f"Deal visual card generated successfully via API for: {deal['startup']}")
                    if download_image(rendered_url, local_img_path):
                        deal["local_image_path"] = local_img_path
                        render_success = True
            
            if not render_success or not os.path.exists(local_img_path):
                resolved_path = deal.get("resolved_image_path")
                if not resolved_path:
                    try:
                        from scripts.render_newscard import resolve_deal_image
                    except ImportError:
                        from render_newscard import resolve_deal_image
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    project_root = os.path.dirname(script_dir)
                    resolved_path = resolve_deal_image(deal, project_root)
                
                if resolved_path and os.path.exists(resolved_path):
                    local_img_path = resolved_path
                    render_success = True
                    print(f"Card render failed. Using clean resolved news image as fallback for {deal['startup']}: {local_img_path}")
            
            if render_success:
                local_image_paths.append(local_img_path)
            else:
                local_image_paths.append(None)
                
        write_markdown_report(deals)
        
        # Send notifications via Gmail
        send_gmail(deals, local_image_paths, investor_img_path, investor_spotlight, test_recipient)
        
        # Send notifications via WhatsApp
        send_whatsapp(deals, test_recipient)
        
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

