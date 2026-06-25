#!/usr/bin/env python3
import os
import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

# Dynamically import PIL
try:
    from PIL import Image
except ImportError:
    print("Pillow library not found. Installing dynamically...")
    import subprocess
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
        from PIL import Image
        print("Pillow library installed successfully.")
    except Exception as e:
        print(f"Failed to install Pillow: {e}")
        sys.exit(1)

# Import render components
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from render_newscard import render_newscard

def send_carousel_email(deal, image_paths, pdf_path, recipient):
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    
    if not gmail_user or not gmail_password:
        print("Missing GMAIL credentials. Cannot send email.")
        return
        
    startup = deal.get("startup", "Unknown Startup")
    amount = deal.get("amount", "Undisclosed")
    subject = f"🎠 [CAROUSEL TEST] {startup} Raises {amount} - Carousel PDF & JPEGs Attached"
    
    html_content = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>The Investor Carousel Briefing</title>
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
                  Carousel Briefing
                </h1>
                <p style="font-family: 'Satoshi', Arial, sans-serif; color: #FFFFFF; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin: 10px 0 0 0;">
                  The Investor Multi-Page PDF & JPEG
                </p>
              </td>
            </tr>
            <tr>
              <td align="left" valign="top" style="padding: 40px 40px 20px 40px; line-height: 1.6;">
                <h2 style="font-family: 'Satoshi', Arial, sans-serif; font-size: 22px; color: #000000; margin: 0 0 20px 0; font-weight: 900; text-transform: uppercase; letter-spacing: -0.5px; border-bottom: 3px solid #000000; padding-bottom: 10px;">
                  Deal Swipe Presentation
                </h2>
                <div style="font-family: 'Satoshi', Arial, sans-serif; font-size: 16px; color: #000000; margin: 0; line-height: 1.6; font-weight: 500;">
                  Here is the multi-slide carousel briefing for <strong>{startup}</strong>. The Cover card is displayed below. The slide details, full JPEGs, and combined PDF presentation are attached as files.
                </div>
              </td>
            </tr>
            <tr>
              <td align="center" valign="top" style="padding: 20px 40px;">
                <img src="cid:carousel_cover" alt="Carousel Cover Card" style="width: 100%; max-width: 520px; height: auto; display: block; border: 3px solid #000000;" />
              </td>
            </tr>
            <tr>
              <td align="center" valign="top" style="background-color: #000000; padding: 40px; border-top: 3px solid #000000;">
                <p style="font-family: 'Satoshi', Arial, sans-serif; color: #FFFFFF; font-size: 18px; font-weight: 900; margin: 0 0 15px 0; letter-spacing: 2px; text-transform: uppercase;">
                  The Investor
                </p>
                <p style="font-family: 'Satoshi', Arial, sans-serif; color: #94A3B8; font-size: 12px; margin: 0 0 25px 0; line-height: 1.6;">
                  You are receiving this test because you are an editor for The Investor capital briefings.
                </p>
                <table border="0" cellpadding="0" cellspacing="0">
                  <tr>
                    <td align="center" style="background-color: #7ED957; border: 2px solid #000000; padding: 10px 24px;">
                      <a href="#" target="_blank" style="font-family: 'Satoshi', Arial, sans-serif; font-size: 14px; color: #000000; font-weight: 900; text-decoration: none; display: inline-block; text-transform: uppercase; letter-spacing: 1px;">
                        Visit platform
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

    print(f"Sending carousel email to {recipient}...")
    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(gmail_user, gmail_password)
        
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = f"The Investor <{gmail_user}>"
        msg['To'] = recipient
        
        # Related part for inline content
        msg_related = MIMEMultipart('related')
        msg.attach(msg_related)
        
        msg_html = MIMEText(html_content, 'html')
        msg_related.attach(msg_html)
        
        # Attach Cover JPEG inline
        cover_path = image_paths[0]
        if os.path.exists(cover_path):
            with open(cover_path, 'rb') as f:
                img_data = f.read()
                msg_img_inline = MIMEImage(img_data)
                msg_img_inline.add_header('Content-ID', '<carousel_cover>')
                msg_related.attach(msg_img_inline)
                
        # Attach all JPEGs as downloadable files
        labels = ["cover", "details", "cta"]
        for idx, img_path in enumerate(image_paths):
            if os.path.exists(img_path):
                with open(img_path, 'rb') as f:
                    msg_img_attach = MIMEImage(f.read())
                    msg_img_attach.add_header('Content-Disposition', 'attachment', filename=f"{startup}_slide_{idx+1}_{labels[idx]}.jpg")
                    msg.attach(msg_img_attach)
                    
        # Attach the compiled PDF
        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                msg_pdf = MIMEBase('application', 'pdf')
                msg_pdf.set_payload(f.read())
                encoders.encode_base64(msg_pdf)
                msg_pdf.add_header('Content-Disposition', 'attachment', filename=os.path.basename(pdf_path))
                msg.attach(msg_pdf)
                
        server.sendmail(gmail_user, recipient, msg.as_string())
        print("Carousel email alert sent successfully!")
        server.quit()
    except Exception as e:
        print(f"Failed to send email: {e}")

def main():
    recipient = "richmondeke@gmail.com"
    if len(sys.argv) > 1 and "@" in sys.argv[1]:
        recipient = sys.argv[1]
        
    print(f"Test carousel recipient set to: {recipient}")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    # Mock deal data
    deal = {
        "startup": "Helix Therapeutics",
        "deal_details": "raised $85 Million Series B",
        "amount": "$85 Million",
        "stage": "Series B",
        "keywords": ["Biotech", "Genomics"],
        "investors": "Arch Venture Partners, Sequoia Capital, F-Prime Capital",
        "summary": "Helix Therapeutics is pioneering high-throughput CRISPR gene-writing platforms to develop single-dose curative therapeutics for rare genetic lung diseases.",
        "source": "TechCrunch",
        "url": "https://techcrunch.com",
        "article_image_url": "https://images.unsplash.com/photo-1530026405186-ed1ea0ac7a63?auto=format&fit=crop&w=800&q=80"
    }
    
    startup_clean = deal["startup"].replace(" ", "_")
    images_dir = os.path.join(project_root, "NewsReport", "images")
    os.makedirs(images_dir, exist_ok=True)
    
    # Setup rendering files
    cover_img_path = os.path.join(images_dir, f"carousel-{startup_clean}-1-cover.jpg")
    details_img_path = os.path.join(images_dir, f"carousel-{startup_clean}-2-details.jpg")
    cta_img_path = os.path.join(images_dir, f"carousel-{startup_clean}-3-cta.jpg")
    pdf_path = os.path.join(images_dir, f"carousel-{startup_clean}-presentation.pdf")
    
    # 1. Render slides
    print("Rendering Slide 1 (Cover)...")
    success_cover = render_newscard(deal, cover_img_path, template_name="newscard.html")
    
    print("Rendering Slide 2 (Details)...")
    success_details = render_newscard(deal, details_img_path, template_name="carousel_details.html")
    
    print("Rendering Slide 3 (CTA)...")
    success_cta = render_newscard(deal, cta_img_path, template_name="carousel_cta.html")
    
    if success_cover and success_details and success_cta:
        print("All slides rendered successfully. Compiling into PDF...")
        try:
            img_cover = Image.open(cover_img_path).convert('RGB')
            img_details = Image.open(details_img_path).convert('RGB')
            img_cta = Image.open(cta_img_path).convert('RGB')
            
            img_cover.save(pdf_path, save_all=True, append_images=[img_details, img_cta])
            print(f"PDF carousel compiled successfully at: {pdf_path}")
            
            # Send test email
            send_carousel_email(deal, [cover_img_path, details_img_path, cta_img_path], pdf_path, recipient)
            
        except Exception as e:
            print(f"Error compiling slides to PDF: {e}")
    else:
        print("Error: One or more slides failed to render.")

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
