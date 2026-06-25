#!/usr/bin/env python3
import os
import re
import sys
import json
import time
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime, timedelta

# Import other components
try:
    import feedparser
    from bs4 import BeautifulSoup
except ImportError:
    pass

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    pass

try:
    from google import genai
    from google.genai import types
except ImportError:
    pass

# Add current dir to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from render_newscard import render_newscard, resolve_deal_image, ensure_playwright

def load_recipients():
    recipients = ["richmondeke@gmail.com"] # Default/Fallback
    csv_path = os.path.join(os.path.dirname(__file__), "..", "recipients.csv")
    if os.path.exists(csv_path):
        try:
            import csv
            with open(csv_path, mode='r') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row and "@" in row[0]:
                        recipients.append(row[0].strip())
        except Exception as e:
            print(f"Error loading recipients: {e}")
    # Unique values
    seen = set()
    return [x for x in recipients if not (x in seen or seen.add(x))]

def get_existing_urls_from_sheets(credentials_path, spreadsheet_name):
    """
    Checks the Google Sheet to retrieve already processed article URLs.
    """
    if not credentials_path or not os.path.exists(credentials_path) or not spreadsheet_name:
        print("Google Sheets credentials or name missing. Skipping sheet duplicate check.")
        return set()
        
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        credentials = Credentials.from_service_account_file(credentials_path, scopes=scope)
        gc = gspread.authorize(credentials)
        sh = gc.open(spreadsheet_name)
        
        urls = set()
        for sheet_name in ["Fundraising Deals", "Breaking News"]:
            try:
                ws = sh.worksheet(sheet_name)
                # URL is Column 5 in standard tab, or Column 5 generally
                col_vals = ws.col_values(5)
                if len(col_vals) > 1:
                    for val in col_vals[1:]:
                        if val.strip():
                            urls.add(val.strip())
            except Exception:
                # Tab may not exist yet
                pass
        return urls
    except Exception as e:
        print(f"Failed to check existing URLs from Google Sheets: {e}")
        return set()

def log_breaking_news_to_sheet(deal, credentials_path, spreadsheet_name):
    """
    Logs the sent breaking news deal to sheets to prevent future duplicates.
    """
    if not credentials_path or not os.path.exists(credentials_path) or not spreadsheet_name:
        return
        
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        credentials = Credentials.from_service_account_file(credentials_path, scopes=scope)
        gc = gspread.authorize(credentials)
        sh = gc.open(spreadsheet_name)
        
        # Log to "Breaking News" sheet
        try:
            ws = sh.worksheet("Breaking News")
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title="Breaking News", rows="100", cols="8")
            ws.append_row(["Date", "Startup", "Deal Details", "Summary", "Source URL", "Keywords", "Score", "Sent Time"])
            
        date_str = datetime.now().strftime("%Y-%m-%d")
        ws.append_row([
            date_str,
            deal.get("startup", "Unknown"),
            deal.get("deal_details", "Unknown"),
            deal.get("summary", ""),
            deal.get("url", ""),
            ", ".join(deal.get("keywords", [])) if isinstance(deal.get("keywords"), list) else str(deal.get("keywords", "")),
            deal.get("score", "5"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])
        print(f"Logged breaking deal {deal.get('startup')} to sheets.")
    except Exception as e:
        print(f"Failed to log breaking news to sheets: {e}")

def fetch_rss_recent(feed_url, source_name, hours_limit=2):
    print(f"Fetching recent articles from {source_name} (cutoff: {hours_limit}h)...")
    feed = feedparser.parse(feed_url)
    articles = []
    cutoff = datetime.now() - timedelta(hours=hours_limit)
    
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
            
    return articles

def parse_with_gemini_filter(articles, gemini_key):
    """
    Evaluates articles using Gemini. Only returns deals that qualify as 5/5
    or are mega deals ($50M+ or major market event).
    """
    if not articles:
        return []
        
    client = genai.Client(api_key=gemini_key)
    prompt = """
    You are an elite venture capital analyst. Analyze the following articles and extract any private funding round announcements.
    For each valid announcement, output a JSON array of objects.
    Each object MUST contain:
    - "startup": name of company raising money
    - "deal_details": clean string of amount & stage (e.g. "raised $30 Million Series B")
    - "amount": the clean amount raised (e.g. "$30 Million")
    - "stage": stage (e.g. "Series B", "Seed", "Grant", "Growth")
    - "keywords": list of 2-3 sector terms
    - "investors": list of lead/participating investors
    - "summary": 2-sentence crisp description of what the company does and details of this raise.
    - "source": name of publication source
    - "url": link to the article
    - "is_african": boolean (true if company operates primarily in Africa or Nigeria)
    - "score": scale 1-5 ranking importance. Give a 5 ONLY for huge rounds (>$50M), unicorn valuations, mega tech acquisitions, or highly notable announcements.

    Output ONLY the valid JSON array. If no funding rounds are found, return: []
    
    Articles:
    """
    
    for idx, art in enumerate(articles):
        prompt += f"\n--- Article {idx+1} ---\nTitle: {art['title']}\nSource: {art['source']}\nURL: {art['link']}\nSummary: {art['description']}\n"
        
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        text = response.text.strip()
        
        try:
            deals = json.loads(text)
        except json.JSONDecodeError:
            json_match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
            if json_match:
                deals = json.loads(json_match.group(0))
            else:
                return []
                
        # Filter for breaking news grade: score == 5 or 5/5 equivalent
        breaking_deals = []
        for d in deals:
            score_val = str(d.get("score", "0"))
            if "5" in score_val:
                breaking_deals.append(d)
                
        return breaking_deals
    except Exception as e:
        print(f"Error parsing with Gemini: {e}")
        return []

def send_breaking_email(deal, image_path, test_recipient=None):
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    
    if not gmail_user or not gmail_password:
        print("Missing GMAIL credentials. Cannot send breaking alert.")
        return
        
    recipients = [test_recipient] if test_recipient else load_recipients()
    if not recipients:
        print("No recipients configured.")
        return
        
    startup = deal.get("startup", "Unknown Startup")
    amount = deal.get("amount", "Undisclosed")
    stage = deal.get("stage", "")
    stage_str = f" ({stage})" if stage else ""
    
    subject = f"🚨 [BREAKING NEWS] {startup} Raises {amount}{stage_str} - The Investor Alert"
    
    # Load and format the email body
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    # Simple inline email template construction
    html_content = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>The Investor Breaking News Alert</title>
  <style type="text/css">
    @import url('https://api.fontshare.com/v2/css?f[]=satoshi@900,700,500,400&display=swap');
    body {{
      margin: 0;
      padding: 0;
      width: 100% !important;
      background-color: #000000;
      font-family: 'Satoshi', 'Helvetica Neue', Arial, sans-serif;
    }}
  </style>
</head>
<body style="margin: 0; padding: 0; background-color: #000000; color: #FFFFFF;">
  <center>
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #000000; padding: 40px 0;">
      <tr>
        <td align="center" valign="top">
          <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #0d0d0d; border: 3px solid #ff3b30; box-shadow: 8px 8px 0px #ff3b30;">
            <tr>
              <td align="center" valign="top" style="background-color: #ff3b30; padding: 30px 20px;">
                <h1 style="font-family: 'Satoshi', Arial, sans-serif; color: #000000; font-size: 28px; font-weight: 900; text-transform: uppercase; letter-spacing: 2px; margin: 0;">
                  BREAKING ALERTS
                </h1>
                <p style="font-family: 'Satoshi', Arial, sans-serif; color: #000000; font-size: 14px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin: 10px 0 0 0;">
                  The Investor Capital Alert
                </p>
              </td>
            </tr>
            <tr>
              <td align="left" valign="top" style="padding: 40px 40px 20px 40px; line-height: 1.6;">
                <h2 style="font-family: 'Satoshi', Arial, sans-serif; font-size: 22px; color: #ff3b30; margin: 0 0 20px 0; font-weight: 900; text-transform: uppercase; letter-spacing: -0.5px;">
                  Breaking Capital Event
                </h2>
                <div style="font-family: 'Satoshi', Arial, sans-serif; font-size: 16px; color: #ffffff; margin: 0; line-height: 1.6; font-weight: 500;">
                  The Investor Editorial Board has confirmed a major market event: <strong>{startup}</strong> has closed a significant funding round of <strong>{amount}</strong>. Check the details on the visual briefing card below.
                </div>
              </td>
            </tr>
            <tr>
              <td align="center" valign="top" style="padding: 20px 40px;">
                <img src="cid:breaking_card_image" alt="Breaking News Card" style="width: 100%; max-width: 520px; height: auto; display: block; border: 3px solid #ff3b30;" />
              </td>
            </tr>
            <tr>
              <td align="center" valign="top" style="background-color: #1a1a1a; padding: 40px; border-top: 3px solid #ff3b30;">
                <p style="font-family: 'Satoshi', Arial, sans-serif; color: #ffffff; font-size: 18px; font-weight: 900; margin: 0 0 15px 0; letter-spacing: 2px; text-transform: uppercase;">
                  The Investor
                </p>
                <p style="font-family: 'Satoshi', Arial, sans-serif; color: #94A3B8; font-size: 12px; margin: 0 0 25px 0; line-height: 1.6;">
                  You are receiving this urgent message because you are subscribed to The Investor breaking capital notifications.
                </p>
                <table border="0" cellpadding="0" cellspacing="0">
                  <tr>
                    <td align="center" style="background-color: #ff3b30; border: 2px solid #ff3b30; padding: 10px 24px;">
                      <a href="https://theinvestor.news" target="_blank" style="font-family: 'Satoshi', Arial, sans-serif; font-size: 14px; color: #000000; font-weight: 900; text-decoration: none; display: inline-block; text-transform: uppercase; letter-spacing: 1px;">
                        View details online
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

    # Send email
    print(f"Connecting to Gmail SMTP to send breaking alert to: {recipients}...")
    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(gmail_user, gmail_password)
        
        for recipient in recipients:
            msg = MIMEMultipart('mixed')
            msg['Subject'] = subject
            msg['From'] = f"The Investor <{gmail_user}>"
            msg['To'] = recipient
            
            # Related container for inline resources
            msg_related = MIMEMultipart('related')
            msg.attach(msg_related)
            
            msg_html = MIMEText(html_content, 'html')
            msg_related.attach(msg_html)
            
            # Attach breaking newscard image inline
            if os.path.exists(image_path):
                with open(image_path, 'rb') as f:
                    img_data = f.read()
                    
                    # 1. Inline version
                    msg_img_inline = MIMEImage(img_data)
                    msg_img_inline.add_header('Content-ID', '<breaking_card_image>')
                    msg_related.attach(msg_img_inline)
                    
                    # 2. Standalone downloadable version
                    msg_img_attach = MIMEImage(img_data)
                    msg_img_attach.add_header('Content-Disposition', 'attachment', filename=os.path.basename(image_path))
                    msg.attach(msg_img_attach)
                    
            server.sendmail(gmail_user, recipient, msg.as_string())
            print(f"Breaking email alert sent successfully to {recipient}!")
            
        server.quit()
    except Exception as e:
        print(f"Failed to send breaking alert emails: {e}")

def main():
    test_recipient = None
    use_mock = False
    
    # Process args
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if "@" in arg:
                test_recipient = arg
                print(f"Test recipient set to: {test_recipient}")
            elif arg in ("--mock", "-m"):
                use_mock = True
                print("Mock mode active.")

    gemini_key = os.environ.get("GEMINI_API_KEY")
    spreadsheet = os.environ.get("SPREADSHEET_NAME")
    sheets_creds = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    
    # Resolve project paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    deals = []
    if use_mock:
        deals = [{
            "startup": "Hyperion Fusion",
            "deal_details": "raised $150 Million Series C",
            "amount": "$150 Million",
            "stage": "Series C",
            "keywords": ["Clean Energy", "Deeptech"],
            "investors": "Helios Ventures, Founders Fund",
            "summary": "Hyperion Fusion is developing pilot-scale clean fusion reactors to provide limitless carbon-free electricity to industrial grids.",
            "source": "TechCrunch",
            "url": "https://hyperionfusion.tech/breaking-news",
            "article_image_url": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=800&q=80",
            "is_african": False,
            "score": 5
        }]
    else:
        # Check sheets for existing duplicates first
        existing_urls = get_existing_urls_from_sheets(sheets_creds, spreadsheet)
        
        # Fetch stories from last 2 hours
        articles = []
        try:
            articles.extend(fetch_rss_recent("https://techcrunch.com/category/venture/feed/", "TechCrunch", 2))
            articles.extend(fetch_rss_recent("https://techcabal.com/feed/", "TechCabal", 2))
            articles.extend(fetch_rss_recent("https://disrupt-africa.com/feed/", "Disrupt Africa", 2))
        except Exception as e:
            print(f"Error fetching feeds: {e}")
            
        # Remove duplicates
        filtered_articles = [a for a in articles if a["link"] not in existing_urls]
        if not filtered_articles:
            print("No new stories to process.")
            return
            
        deals = parse_with_gemini_filter(filtered_articles, gemini_key)
        
    if not deals:
        print("No breaking news capital events found.")
        return
        
    print(f"Found {len(deals)} breaking news events to process.")
    
    for deal in deals:
        startup_clean = deal.get("startup", "deal").replace(" ", "_").replace("/", "_")
        date_str = datetime.now().strftime("%Y-%m-%d")
        image_filename = f"breaking-{date_str}-{startup_clean}-card.jpg"
        save_path = os.path.join(project_root, "NewsReport", "images", image_filename)
        
        # Render using red template
        render_success = False
        try:
            # First download clean og image for the deal
            article_img_url = deal.get("article_image_url")
            if not article_img_url:
                from fetch_and_upload import extract_og_image
                deal["article_image_url"] = extract_og_image(deal.get("url"))
                
            render_success = render_newscard(deal, save_path, template_name="breaking_newscard.html")
        except Exception as e:
            print(f"Error rendering breaking newscard: {e}")
            
        if not render_success:
            # Fallback to resolved image
            resolved_path = resolve_deal_image(deal, project_root)
            if resolved_path and os.path.exists(resolved_path):
                save_path = resolved_path
                render_success = True
                
        if render_success:
            # Send breaking email alert
            send_breaking_email(deal, save_path, test_recipient)
            
            # Log to sheets (tab: "Breaking News")
            if not use_mock:
                log_breaking_news_to_sheet(deal, sheets_creds, spreadsheet)
        else:
            print(f"Failed to generate visuals for breaking deal {deal.get('startup')}. Alert skipped.")

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
