import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Gmail credentials (use app password)
gmail_user = "ekerichmond@gmail.com"
# Remove spaces from the provided password
gmail_app_password = "vwva xodp vzqc ohlx".replace(" ", "")

recipients = ["richmondeke@gmail.com", "masiyerdakol@gmail.com"]
subject = "SyncMaster Newsletter Test"
html = """
<html>
  <body style=\"font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 20px;\">
    <h1 style=\"color: #2c3e50;\">Test Email</h1>
    <p>This is a test of the SyncMaster newsletter automation.</p>
    <p>Feel free to reply with any feedback.</p>
  </body>
</html>
"""

msg = MIMEMultipart("alternative")
msg["Subject"] = subject
msg["From"] = gmail_user
msg["To"] = ", ".join(recipients)
msg.attach(MIMEText(html, "html"))

try:
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_user, gmail_app_password)
        server.sendmail(gmail_user, recipients, msg.as_string())
    print("✅ Test email sent successfully.")
except Exception as e:
    print(f"❌ Failed to send test email: {e}")
