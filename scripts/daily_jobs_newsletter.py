#!/usr/bin/env python3
import os
import re
import sys
import json
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Warning: google-genai is required. Please run pip install google-genai.")
    sys.exit(1)

def fetch_ai_jobs(gemini_key):
    print("Using Gemini API to fetch and structure AI Data Labeling jobs...")
    client = genai.Client(api_key=gemini_key)
    
    prompt = """
    You are an expert AI recruiting researcher. Your task is to use Google Search to find the latest, most relevant remote or hybrid jobs in AI Data Labeling, AI Training, RLHF, and AI Data Operations.
    
    Search for jobs from major AI labs (OpenAI, Anthropic, Google, Scale AI, Surge AI, Outlier, Alignerr, DataAnnotation, etc.) or promising startups that involve:
    - Data Labeling
    - RLHF (Reinforcement Learning from Human Feedback)
    - AI Domain Expert / Writer / Coder for AI Training
    - Data Operations
    
    Extract 5 to 8 of the best, most recent open roles.
    
    Output the results strictly as a JSON array containing objects with these exact keys:
    "title", "company", "description", "requirements", "pay", "url", "score"
    
    - "title": Job Title
    - "company": Company Name
    - "description": 2-3 sentence summary of the role
    - "requirements": Brief comma-separated list of key requirements
    - "pay": The pay range if available (e.g. "$40 - $60/hr"), otherwise "Competitive"
    - "url": The direct application link
    - "score": A score from 1-5 rating the quality/desirability of the job (5 being highest)
    """
    
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )
            
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
            json_match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
            if json_match:
                text = json_match.group(0)
                
            jobs = json.loads(text)
            print(f"Successfully extracted {len(jobs)} jobs.")
            return jobs
        except Exception as e:
            print(f"Attempt {attempt + 1}/3 failed for job fetch: {e}")
            if attempt < 2:
                time.sleep(15 * (attempt + 1))
    return []

def generate_newsletter_html(jobs, gemini_key):
    print("Generating branded newsletter HTML via Gemini...")
    client = genai.Client(api_key=gemini_key)
    date_str = datetime.now().strftime("%B %d, %Y")
    
    jobs_json = json.dumps(jobs, indent=2)
    
    prompt = f"""
    You are a friendly, down-to-earth recruitment editor for Onionlabel, creating a daily newsletter sent to AI Data Labelers, Domain Experts, and Writers.
    
    Generate the HTML content for today's newsletter ({date_str}).
    Use inline CSS inside the HTML style attributes to ensure it renders beautifully in Gmail and other email clients.
    
    The newsletter must follow Onionlabel's design guidelines:
    - Palette: White backgrounds, deep Stripe-like Navy (#06006f) and Stripe Purple (#b696d3) for accents, headers, and buttons.
    - Typography: Clean, modern sans-serif fonts ("Inter", "Helvetica Neue", Arial, sans-serif).
    
    1. Elegant Header: Embed the Onionlabel logo using <img src="https://onionlabel.com/Onionlogoanime.gif" alt="Onionlabel" style="height: 50px; display: block; margin: 0 auto 10px auto;">. Display the edition date and a subtitle below it: "Daily A.I Data Jobs & Opportunities".
    2. Editorial Intro: Write a brief, encouraging introduction about the state of AI training today, keeping it short and relatable.
    3. The Jobs:
       - Format the following jobs nicely: {jobs_json}
       - Create a modern, clean card layout for each job with a light border, rounded corners, and a subtle shadow if possible.
       - Highlight the "company" and "title" prominently (maybe in Navy).
       - Include the "pay" distinctly (maybe in Purple or Green).
       - Provide a clear call-to-action button for the "url" with a solid background (e.g. #06006f) and white text, styled like a pill (border-radius: 999px) with text like "Apply Now".
    4. Premium Footer: Standard newsletter footer with Onionlabel branding, disclaimers, and a link to onionlabel.com.
    
    Return ONLY the raw HTML code. Do not include markdown code block backticks.
    """
    
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            html_code = response.text.strip()
            if html_code.startswith("```html"):
                html_code = html_code[7:]
            elif html_code.startswith("```"):
                html_code = html_code[3:]
            if html_code.endswith("```"):
                html_code = html_code[:-3]
            return html_code.strip()
        except Exception as e:
            print(f"Attempt {attempt + 1}/3 failed for HTML generation: {e}")
            if attempt < 2:
                time.sleep(15 * (attempt + 1))
    return None

def send_email(html_content):
    smtp_host = os.environ.get("SMTP_HOST", "smtp.zoho.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 465))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    
    if not smtp_user or not smtp_password:
        print("Warning: SMTP_USER or SMTP_PASSWORD not set. Cannot send email.")
        return
        
    # By default, sending to the core team or a configured mailing list
    recipients = ["richmondeke@gmail.com", "kamsyosakwe@gmail.com", "masiyerdakol@gmail.com", "troyhodinni@gmail.com", "ekerichmond@gmail.com"]
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"Onionlabel Daily A.I Data Jobs - {date_str}"
    
    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
            
        server.login(smtp_user, smtp_password)
        
        for recipient in recipients:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"Richmond at Onionlabel <{smtp_user}>"
            msg['To'] = recipient
            
            msg_html = MIMEText(html_content, 'html')
            msg.attach(msg_html)
            
            server.sendmail(smtp_user, [recipient], msg.as_string())
            print(f"Sent job newsletter to {recipient}")
            
        server.close()
    except Exception as e:
        print(f"Error sending emails via SMTP: {e}")

if __name__ == "__main__":
    # Load environment variables if running locally
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    env_path = os.path.join(project_root, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    os.environ[k.strip()] = v.strip().strip("'\"")

    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        print("Error: GEMINI_API_KEY is not set.")
        sys.exit(1)
        
    jobs = fetch_ai_jobs(gemini_key)
    
    if not jobs:
        print("No jobs found today.")
        sys.exit(0)
        
    html_content = generate_newsletter_html(jobs, gemini_key)
    
    if html_content:
        send_email(html_content)
    else:
        print("Failed to generate HTML content.")
