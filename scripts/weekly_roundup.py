#!/usr/bin/env python3
import os
import re
import sys
import glob
import smtplib
import argparse
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Warning: google-genai is required. Please run pip install google-genai.")

def load_environment():
    # Load environment variables from .env file if it exists at project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    env_path = os.path.join(project_root, ".env")
    if os.path.exists(env_path):
        print(f"Loading environment variables from {env_path}...")
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    val = v.strip().strip("'\"")
                    os.environ[k.strip()] = val

def load_recent_reports(days=7):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    reports_dir = os.path.join(project_root, "NewsReport")
    
    reports_content = []
    today = datetime.now()
    
    # Generate list of daily filenames for the past 'days' days
    for i in range(days):
        day = today - timedelta(days=i)
        filename = f"{day.strftime('%Y-%m-%d')}-news-report.md"
        filepath = os.path.join(reports_dir, filename)
        if os.path.exists(filepath):
            print(f"Loading daily report: {filepath}")
            with open(filepath, "r", encoding="utf-8") as f:
                reports_content.append(f"--- Report for {day.strftime('%Y-%m-%d')} ---\n" + f.read())
                
    return "\n\n".join(reports_content)

def generate_weekly_html(reports_text, gemini_key):
    print("Compiling weekly roundup HTML via Gemini...")
    client = genai.Client(api_key=gemini_key)
    date_str = datetime.now().strftime("%B %d, %Y")
    
    prompt = f"""
    You are a friendly, down-to-earth financial editor for "The Investor", a weekly private capital & events briefing sent to HNWIs, Family Offices, and Venture Capitalists.
    
    Analyze the following concatenated daily reports from the past week and compile a comprehensive weekly newsletter roundup HTML ({date_str}).
    
    Daily Reports Data:
    {reports_text}
    
    Use inline CSS inside the HTML style attributes to ensure it renders beautifully in Gmail and other email clients.
    
    The weekly newsletter must follow these design guidelines:
    - Palette: Deep rich slate blues (#0F172A), luxurious warm gold/amber accents (#D97706 or #B45309), slate gray for text (#475569), and clean ivory/white backgrounds (#FFFFFF).
    - Typography: Serif headers (e.g. "Georgia", "Garamond", serif) and clean, easy-to-read sans-serif body text (e.g. "Inter", "Helvetica Neue", Arial, sans-serif).
    - Responsive layout with a max-width of 600px, centered, with comfortable padding (20px-30px), soft borders, and premium-looking cards.
    
    The content structure must include:
    1. Elegant Header: Embed the logo using <img src="cid:logo_image" alt="The Investor" style="height: 50px; display: block; margin: 0 auto 10px auto; max-width: 250px;">. Display the edition date and a subtitle below it: "Weekly private capital & events briefing".
    2. Weekly Roundup Intro: Write a friendly, relatable, and simple greeting from Richmond ("Richmond from The Investor"). Keep the tone conversational, down-to-earth, and clear, avoiding complex or pretentious venture capital jargon. Summarize the major themes, trends, or macroeconomic shifts observed in this week's deals in plain English.
    3. Major Deals of the Week:
       - Summarize the top 3-5 deals of the week in a beautifully structured section.
       - Highlight the startup name, amount raised (e.g., "$110 Million"), investors, and a short 2-3 sentence summary of what they do.
    4. Deal Directory (Early Stage & Others):
       - Group or list the rest of the deals by stage or sectors. Keep it compact and clean.
    5. Sponsorship Showcase (Monetization Block):
       - Design a highly styled call-out card encouraging sponsorships.
       - It should look professional and invite sponsors (e.g., "Sponsor The Investor Weekly Briefing. Get in front of thousands of active VCs, HNWIs, and Family Office decision-makers. Contact richmondeke@gmail.com to learn about our sponsorship tiers.").
       - Add a beautiful, styled link/button for "Apply for Sponsorship" linking to `mailto:ekerichmond@gmail.com?subject=Sponsorship%20Inquiry%20-%20The%20Investor%20Weekly`.
    6. HNWI & Family Office Events of the Week:
       - Highlight 2-3 upcoming closed-door networking dinners, private wealth forums, family office summits, or investment syndicate pitch sessions.
       - For each event, provide: Event Name, Date, Location, Target Audience (HNWIs, Family Offices, VCs), a short description, and clear booking details with a styled "Book Seat" button/link. Keep the booking details simple.
    7. Premium Footer: Standard newsletter footer with branding, disclaimers, and subscription terms.
    
    Return ONLY the raw HTML code. Do not include markdown code block backticks (like ```html ... ```) or any additional conversational text. Start with <html> or <!DOCTYPE html> and end with </html>.
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
        print(f"Error generating weekly HTML via Gemini: {e}")
        return None

def send_weekly_email(html_content):
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    
    if not gmail_user or not gmail_password:
        print("Warning: GMAIL_USER or GMAIL_APP_PASSWORD not set. Skipping email sending.")
        return False
        
    recipients = ["richmondeke@gmail.com", "kamsyosakwe@gmail.com"]
    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"The Investor Weekly Briefing - {date_str}"
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    logo_path = os.path.join(project_root, "assets", "TheInvestor.png")
    
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(gmail_user, gmail_password)
        
        for recipient in recipients:
            print(f"Sending weekly email to {recipient}...")
            msg = MIMEMultipart('related')
            msg['Subject'] = subject
            msg['From'] = f"The Investor <{gmail_user}>"
            msg['To'] = recipient
            
            # Attach HTML body
            msg_html = MIMEText(html_content, 'html')
            msg.attach(msg_html)
            
            # Attach logo if present
            if os.path.exists(logo_path):
                try:
                    with open(logo_path, 'rb') as f:
                        logo_data = f.read()
                    msg_logo = MIMEImage(logo_data, name=os.path.basename(logo_path))
                    msg_logo.add_header('Content-ID', '<logo_image>')
                    msg.attach(msg_logo)
                except Exception as e:
                    print(f"Error attaching logo image for {recipient}: {e}")
            
            server.sendmail(gmail_user, [recipient], msg.as_string())
            
        server.close()
        print("All weekly emails sent successfully!")
        return True
    except Exception as e:
        print(f"Error sending emails: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Generate and send the weekly investments newsletter roundup.")
    parser.add_argument("--dry-run", action="store_true", help="Compile and save the weekly report HTML locally without sending emails.")
    parser.add_argument("--days", type=int, default=7, help="Number of days of daily reports to compile (default: 7).")
    args = parser.parse_args()
    
    load_environment()
    
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        print("Error: GEMINI_API_KEY environment variable is not set.")
        sys.exit(1)
        
    print(f"Aggregating reports from the last {args.days} days...")
    reports_text = load_recent_reports(days=args.days)
    if not reports_text:
        print("No daily reports found in the target window. Exiting.")
        sys.exit(0)
        
    html_content = generate_weekly_html(reports_text, gemini_key)
    if not html_content:
        print("Failed to generate weekly newsletter HTML. Exiting.")
        sys.exit(1)
        
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    # Save the output HTML locally for records
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_filename = f"weekly-digest-{date_str}.html"
    output_path = os.path.join(project_root, "NewsReport", output_filename)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Saved weekly digest HTML locally to {output_path}")
    
    if args.dry_run:
        print("Dry run completed. Skipping email distribution.")
    else:
        send_weekly_email(html_content)

if __name__ == "__main__":
    main()
