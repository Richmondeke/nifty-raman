#!/usr/bin/env python3
import os
import sys
import tempfile
import pathlib
import smtplib
import requests
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime

# Import render component
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from render_newscard import ensure_playwright

def get_wikipedia_portrait(name):
    """
    Fetches the high-resolution portrait thumbnail for a given person from the Wikipedia MediaWiki API.
    """
    print(f"Fetching Wikipedia portrait for: {name}...")
    try:
        formatted_name = urllib.parse.quote(name.strip().replace(" ", "_"))
        url = f"https://en.wikipedia.org/w/api.php?action=query&titles={formatted_name}&prop=pageimages&format=json&pithumbsize=1000"
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            pages = data.get("query", {}).get("pages", {})
            for page_id, page in pages.items():
                if "thumbnail" in page:
                    img_url = page["thumbnail"]["source"]
                    print(f"Wikipedia portrait found: {img_url}")
                    return img_url
        print("No Wikipedia portrait found. Using fallback.")
    except Exception as e:
        print(f"Error fetching Wikipedia portrait: {e}")
    return None

def render_spotlight_card(item, save_path):
    print("Rendering spotlight card...")
    if not ensure_playwright():
        print("Playwright check failed.")
        return False
        
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    template_path = os.path.join(project_root, "templates", "spotlight_card.html")
    
    if not os.path.exists(template_path):
        print(f"Template not found at {template_path}")
        return False
        
    with open(template_path, "r", encoding="utf-8") as f:
        template_content = f.read()
        
    # Get logo path
    logo_path = os.path.join(project_root, "assets", "TheInvestor.png")
    logo_uri = pathlib.Path(logo_path).as_uri()
    
    # Placeholders replacement
    html_content = template_content
    html_content = html_content.replace("{logo_uri}", logo_uri)
    html_content = html_content.replace("{date}", datetime.now().strftime("%B %d, %Y"))
    
    for key, val in item.items():
        html_content = html_content.replace(f"{{{key}}}", str(val))
        
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
            
        print(f"Successfully rendered spotlight card to: {save_path}")
        return True
    except Exception as e:
        print(f"Failed to render spotlight card: {e}")
        return False
    finally:
        if os.path.exists(temp_html_path):
            os.remove(temp_html_path)

def send_spotlight_email(item, image_path, recipient):
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    
    if not gmail_user or not gmail_password:
        print("Missing GMAIL credentials. Skipping email dispatch.")
        return
        
    subject = f"🏢 [INSIGHTS] Billionaire Spotlight: {item['person_name']}"
    
    # Email HTML body template
    html_content = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>The Investor Spotlight Briefing</title>
</head>
<body style="margin: 0; padding: 0; background-color: #FFFFFF; font-family: Arial, sans-serif;">
  <center>
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #FFFFFF; max-width: 650px;">
      <tr>
        <td align="center" valign="top" style="padding: 20px 0 30px 0;">
          <img src="cid:spotlight_card_image" width="100%" style="max-width: 600px; display: block; border: none; height: auto;" />
        </td>
      </tr>
      <tr>
        <td align="center" valign="top" style="background-color: #151515; padding: 40px; border-top: 3px solid #7ED957;">
          <p style="font-family: Arial, sans-serif; color: #ffffff; font-size: 18px; font-weight: bold; margin: 0 0 15px 0; letter-spacing: 2px; text-transform: uppercase;">
            The Investor
          </p>
          <p style="font-family: Arial, sans-serif; color: #94A3B8; font-size: 12px; margin: 0 0 25px 0; line-height: 1.6;">
            You are receiving this premium digest because you are subscribed to The Investor insights notifications.
          </p>
          <table border="0" cellpadding="0" cellspacing="0">
            <tr>
              <td align="center" style="background-color: #7ED957; border: 2px solid #7ED957; padding: 10px 24px;">
                <a href="#" target="_blank" style="font-family: Arial, sans-serif; font-size: 14px; color: #000000; font-weight: bold; text-decoration: none; display: inline-block; text-transform: uppercase; letter-spacing: 1px;">
                  Explore Collection
                </a>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </center>
</body>
</html>"""

    print(f"Connecting to SMTP to send spotlight email to: {recipient}...")
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
                
                # Inline attachment
                msg_img_inline = MIMEImage(img_data)
                msg_img_inline.add_header('Content-ID', '<spotlight_card_image>')
                msg_related.attach(msg_img_inline)
                
                # File attachment
                msg_img_attach = MIMEImage(img_data)
                msg_img_attach.add_header('Content-Disposition', 'attachment', filename=os.path.basename(image_path))
                msg.attach(msg_img_attach)
                
        server.sendmail(gmail_user, recipient, msg.as_string())
        print("Spotlight email sent successfully!")
        server.quit()
    except Exception as e:
        print(f"Failed to send spotlight email: {e}")

def main():
    recipient = "richmondeke@gmail.com"
    if len(sys.argv) > 1 and "@" in sys.argv[1]:
        recipient = sys.argv[1]
        
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    # 1. Target Spotlight Person
    person_name = "Aliko Dangote"
    person_title = "Founder, Chairman & CEO of Dangote Group"
    net_worth = "$13.9 Billion"
    source_wealth = "Cement, Sugar, Flour, Oil"
    quote = "If you don't have ambition, you shouldn't be alive. Nothing is going to be handed to you on a silver platter."
    
    portrait_url = get_wikipedia_portrait(person_name)
    if not portrait_url:
        # Premium fallback portrait (generic business suit profile)
        portrait_url = "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=800&q=80"
        
    item = {
        "person_name": person_name,
        "person_title": person_title,
        "net_worth": net_worth,
        "source_wealth": source_wealth,
        "quote": quote,
        "portrait_image": portrait_url
    }
    
    images_dir = os.path.join(project_root, "NewsReport", "images")
    os.makedirs(images_dir, exist_ok=True)
    save_path = os.path.join(images_dir, f"spotlight-{datetime.now().strftime('%Y-%m-%d')}-{person_name.replace(' ', '_')}.jpg")
    
    if render_spotlight_card(item, save_path):
        send_spotlight_email(item, save_path, recipient)

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
