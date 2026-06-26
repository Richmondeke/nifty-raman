#!/usr/bin/env python3
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Load credentials from .env
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
gmail_user = None
gmail_pass = None

if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            if line.startswith("GMAIL_USER="):
                gmail_user = line.split("=", 1)[1].strip()
            elif line.startswith("GMAIL_APP_PASSWORD="):
                gmail_pass = line.split("=", 1)[1].strip()

# Target recipient
to_email = "richmondeke@gmail.com"

if not gmail_user or not gmail_pass:
    print("Error: SMTP credentials not found in .env file.")
    sys.exit(1)

# Compose Email
msg = MIMEMultipart("alternative")
msg["Subject"] = "The Investor — Dashboard Integration & Scraper Optimization Completion Report"
msg["From"] = f"The Investor Dev Team <{gmail_user}>"
msg["To"] = to_email

html_content = """
<html>
<head>
  <style>
    body {
      font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
      background-color: #030712;
      color: #f8fafc;
      margin: 0;
      padding: 0;
    }
    .container {
      max-width: 600px;
      margin: 30px auto;
      background-color: #0f172a;
      border: 1px solid #1e293b;
      border-radius: 16px;
      padding: 40px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    }
    .header {
      border-bottom: 1px solid #334155;
      padding-bottom: 20px;
      margin-bottom: 30px;
      text-align: center;
    }
    .logo {
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.5px;
      background: linear-gradient(135deg, #d4fc34, #10b981);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      display: inline-block;
    }
    h1 {
      font-size: 20px;
      margin-top: 10px;
      color: #f8fafc;
    }
    h2 {
      font-size: 16px;
      color: #d4fc34;
      margin-top: 25px;
      text-transform: uppercase;
      letter-spacing: 1px;
    }
    p, li {
      font-size: 14px;
      line-height: 1.6;
      color: #94a3b8;
    }
    ul {
      padding-left: 20px;
    }
    li {
      margin-bottom: 8px;
    }
    .highlight {
      color: #f8fafc;
      font-weight: bold;
    }
    .footer {
      border-top: 1px solid #334155;
      padding-top: 20px;
      margin-top: 40px;
      text-align: center;
      font-size: 12px;
      color: #64748b;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="logo">THE INVESTOR</div>
      <h1>Engineering Completion Report</h1>
    </div>
    
    <p>Hi Richmond,</p>
    <p>We are pleased to report that the multi-channel scheduling dashboard and system optimizations have been successfully implemented and deployed locally.</p>
    
    <h2>1. Multi-Channel Scheduling Dashboard</h2>
    <ul>
      <li><span class="highlight">Rwazi Glassmorphic Design:</span> Adopted the premium dark tech spec with outline SVG icons, clean borders, and a canvas-based grid mesh wave animation.</li>
      <li><span class="highlight">Connected Channels Sidebar:</span> A persistent panel displaying connected channels. LinkedIn is active with "The Investor" page name. Stubs for Twitter/X and Meta (Facebook, Instagram) are integrated with connect modals to simulate credential bindings.</li>
      <li><span class="highlight">Composer & Mockup:</span> Supports composing posts, attaching generated cards directly from the briefing directories, and features a real-time LinkedIn post preview box.</li>
      <li><span class="highlight">Editorial Calendar:</span> Monthly scheduler layout that shows pending, published, and failed briefings on their respective days with detail view popups to reschedule.</li>
      <li><span class="highlight">Kanban Workflow:</span> Three columns tracking scheduled, published, and failed tasks with action buttons (Publish Now, Retry, Delete).</li>
    </ul>

    <h2>2. System Fixes & Optimization</h2>
    <ul>
      <li><span class="highlight">Pinterest Search:</span> Resolved the 30-second Scrapy/Playwright timeouts by adjusting the wait state from <code style="color:#d4fc34">networkidle</code> to <code style="color:#d4fc34">domcontentloaded</code> in the search script.</li>
      <li><span class="highlight">Wikipedia Scraper:</span> Bypassed Wikipedia API's 403 blocking issue on portraits (like Aliko Dangote) by implementing proper user-agent headers.</li>
      <li><span class="highlight">OAuth Redirect Route:</span> Fixed a missing <code style="color:#d4fc34">urllib.parse</code> import crash issue on the callback routing.</li>
    </ul>

    <h2>3. Local Access Instructions</h2>
    <p>The server is running locally on your Mac at: <a href="http://localhost:8080/" style="color:#d4fc34; text-decoration:none; font-weight:bold;">http://localhost:8080/</a></p>
    
    <p>You can view and test the interface directly in your browser. Since you authorized access earlier, the dashboard is fully operational and authenticated with LinkedIn.</p>

    <div class="footer">
      This is an automated system confirmation email.
    </div>
  </div>
</body>
</html>
"""

part2 = MIMEText(html_content, "html")
msg.attach(part2)

try:
    print(f"Connecting to Gmail SMTP server on behalf of {gmail_user}...")
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(gmail_user, gmail_pass)
    print("Authentication successful. Sending email...")
    server.sendmail(gmail_user, to_email, msg.as_string())
    server.quit()
    print("Email sent successfully!")
except Exception as e:
    print(f"Failed to send email: {e}")
    sys.exit(1)
