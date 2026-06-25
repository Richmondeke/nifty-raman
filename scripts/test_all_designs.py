#!/usr/bin/env python3
import os
import sys
import tempfile
import pathlib
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime

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
                      <a href="https://theinvestor.news" target="_blank" style="font-family: 'Satoshi', Arial, sans-serif; font-size: 14px; color: #000000; font-weight: 900; text-decoration: none; display: inline-block; text-transform: uppercase; letter-spacing: 1px;">
                        theinvestor.news
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

def main():
    recipient = "richmondeke@gmail.com"
    if len(sys.argv) > 1 and "@" in sys.argv[1]:
        recipient = sys.argv[1]
        
    print(f"Target design showcase recipient: {recipient}")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    images_dir = os.path.join(project_root, "NewsReport", "images")
    os.makedirs(images_dir, exist_ok=True)
    
    # Mock Data Sets
    daily_deal = {
        "startup": "Shield AI",
        "deal_image": "https://images.unsplash.com/photo-1508962914676-134849a727f0?auto=format&fit=crop&w=800&q=80",
        "amount": "$200 Million",
        "stage": "Series F",
        "industry": "Defense Tech",
        "investors": "U.S. Innovative Technology Fund, Riot Ventures",
        "summary": "Shield AI builds autonomous pilot software for military aircraft. Their technology enables jet fighters and quadcopters to navigate and complete tactical missions without GPS or communications links."
    }
    
    breaking_deal = {
        "startup": "Retool Corp",
        "deal_image": "https://images.unsplash.com/photo-1498050108023-c5249f4df085?auto=format&fit=crop&w=800&q=80",
        "amount": "$45 Million",
        "stage": "Series C",
        "industry": "Developer Tools",
        "investors": "Sequoia Capital, Y Combinator, Patrick Collison",
        "summary": "Retool is a low-code platform that lets developers construct internal database dashboards and client administration tools up to 10x faster."
    }
    
    job_role = {
        "role_title": "Lead Venture Analyst",
        "company": "The Investor Ventures",
        "salary": "$140,000 - $180,000",
        "location": "Lagos, Nigeria (Hybrid)",
        "sector": "Private Capital",
        "requirements": "Looking for a high-performing VC analyst with 3+ years experience evaluating African tech series A deals. Must be proficient in financial modeling and cap table audit workflows."
    }
    
    event_data = {
        "event_title": "Family Office Private Dinner",
        "organizer": "The Investor Board",
        "location": "Victoria Island, Lagos",
        "venue": "The Capital Club Lounge",
        "description": "An invite-only private dining experience connecting Nigerian family office managers, HNWI allocators, and top venture fund GPs to discuss stealth private capital deals."
    }
    
    lifestyle_item = {
        "price": "$28,000",
        "item_image": "https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=800&q=80",
        "category": "Horology",
        "item_name": "Royal Oak Green Dial",
        "maker": "Audemars Piguet",
        "model": "Ref. 15510ST.OO.1320ST.04",
        "spec_val_1": "Forest Green 'Grande Tapisserie'",
        "spec_val_2": "Stainless Steel Bracelet",
        "description": "This Audemars Piguet Royal Oak Selfwinding features a stainless steel case, an integrated bracelet, and an elegant forest green dial with the signature Tapisserie guilloché pattern."
    }
    
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
