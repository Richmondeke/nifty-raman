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
    import google.generativeai as genai
except ImportError:
    print("Warning: google-generativeai is required.")

def fetch_techcrunch_deals():
    print("Fetching TechCrunch Venture deals...")
    feed_url = "https://techcrunch.com/category/venture/feed/"
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
                "source": "TechCrunch"
            })
        except Exception as e:
            print(f"Error parsing TC entry: {e}")
            
    print(f"Retrieved {len(articles)} recent articles from TechCrunch.")
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
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        print("Error: GEMINI_API_KEY environment variable is not set. Cannot run LLM parsing.")
        sys.exit(1)
        
    genai.configure(api_key=gemini_key)
    input_text = json.dumps(articles, indent=2)
    
    prompt = f"""
    You are an expert venture capital researcher. Analyze the following articles and extract only actual startup fundraising announcements or venture capital deals. Ignore general tech tutorials, product updates, M&As (unless major), or opinion essays.
    
    For each valid deal, extract:
    1. Startup Name
    2. Deal details (amount and stage, e.g. "$15 Million Series A", "$5 Million Seed", "undisclosed Series B")
    3. Clean Amount Raised (strictly formatted like "$110 Million", "$50 Billion", "$500 Thousand". If undisclosed, use "Undisclosed")
    4. Clean Stage (keep it extremely simple, e.g. "Preseed", "Seed", "Series A", "Series B", "Series C", "Series D", "Growth", "M&A", "Debt", "Undisclosed". Do not add extra words)
    5. Summary (2-4 sentences explaining what the company does and why it is notable)
    6. Lead/Participating Investors
    7. Source Domain (e.g. "TechCrunch" or "Hacker News")
    8. URL
    9. Keywords (3-4 relevant tags, e.g. "healthtech", "AI-infrastructure", "saas")
    10. Quality Score (1 to 5, where 5 is a massive/groundbreaking deal, 3 is standard, 1 is minor)
    
    Output the results strictly as a JSON array containing objects with these exact keys:
    "startup", "deal_details", "amount", "stage", "summary", "investors", "source", "url", "keywords", "score"
    
    Articles Data:
    {input_text}
    """
    
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        
        deals = json.loads(response.text)
        print(f"Gemini successfully extracted {len(deals)} deals.")
        return deals
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return []

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

def send_gmail(deals, local_image_path=None):
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    
    if not gmail_user or not gmail_password:
        print("Warning: GMAIL_USER or GMAIL_APP_PASSWORD not set. Skipping Gmail notification.")
        return
        
    print(f"Sending email notification to {gmail_user}...")
    msg = MIMEMultipart('related')
    date_str = datetime.now().strftime("%Y-%m-%d")
    msg['Subject'] = f"Daily Fundraising News Report ({date_str})"
    msg['From'] = gmail_user
    msg['To'] = gmail_user
    
    # HTML Email body
    html_parts = [
        "<html>",
        "<body style='font-family: Arial, sans-serif; color: #333; line-height: 1.6;'>",
        f"<h2 style='color: #004085;'>Daily Startup Fundraising News Report ({date_str})</h2>",
        f"<p>Curated from TechCrunch and Hacker News. Contains {len(deals)} fundraising deals.</p>"
    ]
    
    # Embed top deal card image at the top of the email
    if local_image_path and os.path.exists(local_image_path):
        html_parts.append("<div style='margin: 20px 0;'>")
        html_parts.append("  <img src='cid:top_deal_image' style='max-width: 600px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);'>")
        html_parts.append("</div>")
        
    html_parts.append("<hr style='border: 0; border-top: 1px solid #ddd; margin: 20px 0;'>")
    
    for i, d in enumerate(deals, 1):
        html_parts.append(f"<div style='margin-bottom: 25px;'>")
        html_parts.append(f"  <h3 style='margin: 0 0 10px 0; color: #333;'>{i}. {d.get('startup')}: {d.get('deal_details')}</h3>")
        html_parts.append(f"  <p style='margin: 0 0 10px 0;'><strong>Summary:</strong> {d.get('summary')}</p>")
        html_parts.append(f"  <p style='margin: 0 0 10px 0;'><strong>Investors:</strong> {d.get('investors', 'Undisclosed')}</p>")
        
        kws = d.get('keywords', [])
        kw_str = ", ".join(kws) if isinstance(kws, list) else str(kws)
        html_parts.append(f"  <p style='margin: 0 0 10px 0;'><strong>Sector Keywords:</strong> {kw_str}</p>")
        html_parts.append(f"  <p style='margin: 0;'><strong>Source:</strong> <a href='{d.get('url')}' style='color: #007bff; text-decoration: none;'>{d.get('source')}</a></p>")
        html_parts.append(f"</div>")
        html_parts.append("<hr style='border: 0; border-top: 1px solid #eee; margin: 20px 0;'>")
        
    html_parts.append(f"<p style='font-size: 11px; color: #888;'>Generated automatically by Daily News Report v3.0.</p>")
    html_parts.append("</body>")
    html_parts.append("</html>")
    
    msg_html = MIMEText("\n".join(html_parts), 'html')
    msg.attach(msg_html)
    
    # Attach embedded image
    if local_image_path and os.path.exists(local_image_path):
        try:
            with open(local_image_path, 'rb') as f:
                img_data = f.read()
            msg_img = MIMEImage(img_data, name=os.path.basename(local_image_path))
            msg_img.add_header('Content-ID', '<top_deal_image>')
            msg.attach(msg_img)
        except Exception as e:
            print(f"Error attaching inline image to Gmail: {e}")
            
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, [gmail_user], msg.as_string())
        server.close()
        print("Daily report email sent successfully via Gmail!")
    except Exception as e:
        print(f"Error sending email via Gmail: {e}")

if __name__ == "__main__":
    # Load environment variables from .env file if it exists
    if os.path.exists(".env"):
        print("Loading environment variables from .env...")
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

    # Check secrets/config
    spreadsheet = os.environ.get("SPREADSHEET_NAME")
    
    # Render API credentials
    templated_key = os.environ.get("TEMPLATED_API_KEY")
    templated_id = os.environ.get("TEMPLATED_TEMPLATE_ID")
    
    creatomate_key = os.environ.get("CREATOMATE_API_KEY")
    creatomate_id = os.environ.get("CREATOMATE_TEMPLATE_ID")
        
    articles = []
    articles.extend(fetch_techcrunch_deals())
    articles.extend(fetch_hn_deals())
    
    if not articles:
        print("No articles fetched. Exiting.")
        sys.exit(0)
        
    deals = parse_with_gemini(articles)
    if deals:
        # Sort deals by quality score descending to find the top deal of the day
        try:
            deals.sort(key=lambda d: int(d.get("score", 0)), reverse=True)
        except Exception as e:
            print(f"Error sorting deals: {e}")

        # Generate visual asset only for the top deal of the day (1 render per day constraint)
        top_deal = deals[0]
        rendered_url = None
        if templated_key and templated_id:
            rendered_url = render_templated_card(top_deal, templated_key, templated_id)
        elif creatomate_key and creatomate_id:
            rendered_url = render_creatomate_card(top_deal, creatomate_key, creatomate_id)
        
        local_img_path = None
        if rendered_url:
            top_deal["rendered_image_url"] = rendered_url
            print(f"Top deal visual card generated successfully for: {top_deal['startup']}")
            
            # Download and save the image locally
            date_str = datetime.now().strftime("%Y-%m-%d")
            image_filename = f"{date_str}-top-deal.jpg"
            local_img_path = os.path.join("NewsReport", "images", image_filename)
            if download_image(rendered_url, local_img_path):
                top_deal["local_image_path"] = local_img_path
                
        write_markdown_report(deals)
        
        # Send notifications via Gmail
        send_gmail(deals, local_img_path)
        
        if spreadsheet:
            sheets_creds = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
            upload_to_sheets(deals, sheets_creds, spreadsheet)
    else:
        print("No deals found after LLM extraction.")
