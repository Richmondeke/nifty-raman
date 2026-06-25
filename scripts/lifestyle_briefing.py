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

# Dynamically import PIL
try:
    from PIL import Image
except ImportError:
    import subprocess
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
        from PIL import Image
    except Exception as e:
        print(f"Failed to install Pillow: {e}")
        sys.exit(1)

# Import render components
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from render_newscard import ensure_playwright

def render_lifestyle_card(item, save_path):
    """
    Renders the lifestyle HTML template to a JPEG image using Playwright.
    """
    print(f"Rendering lifestyle card for {item.get('item_name')} via Playwright...")
    if not ensure_playwright():
        print("Skipping Playwright render: environment setup failed.")
        return False
        
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    template_path = os.path.join(project_root, "templates", "lifestyle_newscard.html")
    
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
    html_content = html_content.replace("{price}", item.get("price", "Upon Request"))
    html_content = html_content.replace("{item_image}", item.get("item_image", ""))
    html_content = html_content.replace("{category}", item.get("category", "Luxury"))
    html_content = html_content.replace("{item_name}", item.get("item_name", "Luxury Item"))
    html_content = html_content.replace("{maker}", item.get("maker", "Unknown"))
    html_content = html_content.replace("{model}", item.get("model", "Unknown"))
    html_content = html_content.replace("{spec_val_1}", item.get("spec_val_1", "Unknown"))
    html_content = html_content.replace("{spec_val_2}", item.get("spec_val_2", "Unknown"))
    html_content = html_content.replace("{description}", item.get("description", ""))
    
    # Write to a temporary HTML file
    temp_fd, temp_html_path = tempfile.mkstemp(suffix=".html")
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        # Use Playwright to capture screenshot
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1080, "height": 1350})
            page.goto(pathlib.Path(temp_html_path).as_uri())
            page.wait_for_load_state("networkidle")
            
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            page.screenshot(path=save_path, type="jpeg", quality=90, full_page=True)
            browser.close()
            
        print(f"Successfully rendered and saved lifestyle card to: {save_path}")
        return True
        
    except Exception as e:
        print(f"Error during Playwright rendering: {e}")
        return False
    finally:
        if os.path.exists(temp_html_path):
            os.remove(temp_html_path)

def send_lifestyle_email(item, image_path, recipient):
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    
    if not gmail_user or not gmail_password:
        print("Missing GMAIL credentials. Cannot send email.")
        return
        
    item_name = item.get("item_name", "Luxury Item")
    price = item.get("price", "Upon Request")
    subject = f"💎 [LIFESTYLE ALERT] {item_name} ({price}) - The Investor Luxury Showcase"
    
    html_content = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>The Investor Luxury Showcase</title>
  <style type="text/css">
    @import url('https://api.fontshare.com/v2/css?f[]=satoshi@900,700,500,400&display=swap');
    body {{
      margin: 0;
      padding: 0;
      width: 100% !important;
      background-color: #050505;
      font-family: 'Satoshi', 'Helvetica Neue', Arial, sans-serif;
    }}
  </style>
</head>
<body style="margin: 0; padding: 0; background-color: #050505; color: #FFFFFF;">
  <center>
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #050505; padding: 40px 0;">
      <tr>
        <td align="center" valign="top">
          <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #0a0a0a; border: 3px solid #d4af37; box-shadow: 8px 8px 0px #d4af37;">
            <tr>
              <td align="center" valign="top" style="background-color: #d4af37; padding: 30px 20px;">
                <h1 style="font-family: 'Satoshi', Arial, sans-serif; color: #000000; font-size: 28px; font-weight: 900; text-transform: uppercase; letter-spacing: 2px; margin: 0;">
                  LIFESTYLE SHOWCASE
                </h1>
                <p style="font-family: 'Satoshi', Arial, sans-serif; color: #000000; font-size: 14px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin: 10px 0 0 0;">
                  The Investor Premium Digest
                </p>
              </td>
            </tr>
            <tr>
              <td align="left" valign="top" style="padding: 40px 40px 20px 40px; line-height: 1.6;">
                <h2 style="font-family: 'Satoshi', Arial, sans-serif; font-size: 22px; color: #d4af37; margin: 0 0 20px 0; font-weight: 900; text-transform: uppercase; letter-spacing: -0.5px;">
                  Exclusive Collection Spotlight
                </h2>
                <div style="font-family: 'Satoshi', Arial, sans-serif; font-size: 16px; color: #ffffff; margin: 0; line-height: 1.6; font-weight: 500;">
                  Our editorial curators highlight the <strong>{item_name}</strong>. Details, specs, and estimated values are featured in the luxury briefing card below.
                </div>
              </td>
            </tr>
            <tr>
              <td align="center" valign="top" style="padding: 20px 40px;">
                <img src="cid:lifestyle_card_image" alt="Lifestyle Showcase Card" style="width: 100%; max-width: 520px; height: auto; display: block; border: 3px solid #d4af37;" />
              </td>
            </tr>
            <tr>
              <td align="center" valign="top" style="background-color: #151515; padding: 40px; border-top: 3px solid #d4af37;">
                <p style="font-family: 'Satoshi', Arial, sans-serif; color: #ffffff; font-size: 18px; font-weight: 900; margin: 0 0 15px 0; letter-spacing: 2px; text-transform: uppercase;">
                  The Investor
                </p>
                <p style="font-family: 'Satoshi', Arial, sans-serif; color: #94A3B8; font-size: 12px; margin: 0 0 25px 0; line-height: 1.6;">
                  You are receiving this premium digest because you are subscribed to The Investor luxury notifications.
                </p>
                <table border="0" cellpadding="0" cellspacing="0">
                  <tr>
                    <td align="center" style="background-color: #d4af37; border: 2px solid #d4af37; padding: 10px 24px;">
                      <a href="https://theinvestor.news" target="_blank" style="font-family: 'Satoshi', Arial, sans-serif; font-size: 14px; color: #000000; font-weight: 900; text-decoration: none; display: inline-block; text-transform: uppercase; letter-spacing: 1px;">
                        Explore Collection
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

    print(f"Connecting to SMTP to send lifestyle alert to: {recipient}...")
    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(gmail_user, gmail_password)
        
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = f"The Investor <{gmail_user}>"
        msg['To'] = recipient
        
        # Related part
        msg_related = MIMEMultipart('related')
        msg.attach(msg_related)
        
        msg_html = MIMEText(html_content, 'html')
        msg_related.attach(msg_html)
        
        # Attach card image inline
        if os.path.exists(image_path):
            with open(image_path, 'rb') as f:
                img_data = f.read()
                
                # Inline version
                msg_img_inline = MIMEImage(img_data)
                msg_img_inline.add_header('Content-ID', '<lifestyle_card_image>')
                msg_related.attach(msg_img_inline)
                
                # File attachment
                msg_img_attach = MIMEImage(img_data)
                msg_img_attach.add_header('Content-Disposition', 'attachment', filename=os.path.basename(image_path))
                msg.attach(msg_img_attach)
                
        server.sendmail(gmail_user, recipient, msg.as_string())
        print("Lifestyle email alert sent successfully!")
        server.quit()
    except Exception as e:
        print(f"Failed to send lifestyle email: {e}")

def main():
    recipient = "richmondeke@gmail.com"
    if len(sys.argv) > 1 and "@" in sys.argv[1]:
        recipient = sys.argv[1]
        
    print(f"Test lifestyle recipient set to: {recipient}")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    # Mock luxury item details
    item = {
        "price": "$380,000",
        "item_image": "https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=800&q=80",
        "category": "Watch",
        "item_name": "Cosmograph Daytona Platinum",
        "maker": "Rolex",
        "model": "Ref. 126506-0001",
        "spec_val_1": "Ice Blue Dial",
        "spec_val_2": "Chestnut Brown Ceramic",
        "description": "The Rolex Cosmograph Daytona in 950 platinum features an ice blue dial and a chestnut brown Cerachrom bezel. It is equipped with the calibre 4131 chronograph movement and features a transparent sapphire case back."
    }
    
    images_dir = os.path.join(project_root, "NewsReport", "images")
    os.makedirs(images_dir, exist_ok=True)
    save_path = os.path.join(images_dir, f"lifestyle-{datetime.now().strftime('%Y-%m-%d')}-Daytona.jpg")
    
    if render_lifestyle_card(item, save_path):
        send_lifestyle_email(item, save_path, recipient)

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
