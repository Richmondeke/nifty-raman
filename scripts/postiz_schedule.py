import os
import sys
import glob
import subprocess
from datetime import datetime, timedelta, timezone

def schedule_post():
    integration_id = os.environ.get("POSTIZ_INTEGRATION_ID")
    if not integration_id:
        print("POSTIZ_INTEGRATION_ID not set. Skipping post scheduling.")
        return

    date_str = datetime.now().strftime("%Y-%m-%d")
    image_path = os.path.join("NewsReport", "images", f"{date_str}-top-deal.jpg")
    
    post_text = f"📰 Today's Venture Capital Briefing is out!\n\nCheck out the top startup deals of the day! 📈💸\n\n#VentureCapital #Startups #Fundraising #TechNews"
    
    media_arg = []
    if os.path.exists(image_path):
        # Media path must be absolute for many CLIs
        abs_image_path = os.path.abspath(image_path)
        media_arg = ["-m", abs_image_path]
        
    # Schedule for 15 minutes from now
    schedule_time = (datetime.now(timezone.utc) + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    cmd = [
        "postiz", "posts:create",
        "-c", post_text,
        "-s", schedule_time,
        "-i", integration_id,
    ] + media_arg
    
    print("Running Postiz scheduling command...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    print("Postiz STDOUT:", result.stdout)
    if result.stderr:
        print("Postiz STDERR:", result.stderr)
        
    if result.returncode != 0:
        print(f"Failed to schedule post via Postiz (exit code {result.returncode})")
        sys.exit(1)
    else:
        print("Post successfully scheduled via Postiz!")

if __name__ == "__main__":
    schedule_post()
