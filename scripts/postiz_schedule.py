import os
import sys
import json
import subprocess
from datetime import datetime, timedelta, timezone

def upload_to_postiz(image_path):
    print(f"Uploading {image_path} to Postiz...")
    cmd = ["postiz", "upload", image_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("Upload successful!")
        try:
            # Try to find JSON in output
            json_str = result.stdout[result.stdout.find('{'):result.stdout.rfind('}')+1]
            data = json.loads(json_str)
            return data.get("path")
        except Exception as e:
            print(f"Could not parse upload URL: {e}")
            return None
    else:
        print(f"Upload failed: {result.stderr}")
        return None

def schedule_post():
    integration_ids_str = os.environ.get("POSTIZ_INTEGRATION_ID")
    if not integration_ids_str:
        print("POSTIZ_INTEGRATION_ID not set. Skipping post scheduling.")
        return

    integration_ids = [i.strip() for i in integration_ids_str.split(",") if i.strip()]
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    image_path = os.path.join("NewsReport", "images", f"{date_str}-top-deal.jpg")
    
    post_text = f"📰 Today's Venture Capital Briefing is out!\n\nCheck out the top startup deals of the day! 📈💸\n\n#VentureCapital #Startups #Fundraising #TechNews"
    
    uploaded_url = None
    if os.path.exists(image_path):
        uploaded_url = upload_to_postiz(os.path.abspath(image_path))

    # Schedule for 15 minutes from now
    schedule_time = (datetime.now(timezone.utc) + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    any_failed = False
    
    for int_id in integration_ids:
        print(f"Scheduling post for integration {int_id}...")
        cmd = [
            "postiz", "posts:create",
            "-c", post_text,
            "-s", schedule_time,
            "-i", int_id,
        ]
        
        if uploaded_url:
            cmd.extend(["-m", uploaded_url, "--settings", '{"post_type":"post"}'])
            
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(f"Postiz STDOUT for {int_id}:", result.stdout)
        if result.stderr:
            print(f"Postiz STDERR for {int_id}:", result.stderr)
            
        if result.returncode != 0:
            print(f"Failed to schedule post for integration {int_id} (exit code {result.returncode})")
            any_failed = True
        else:
            print(f"Post successfully scheduled for {int_id}!")
            
    if any_failed:
        print("One or more posts failed to schedule.")
        sys.exit(1)

if __name__ == "__main__":
    schedule_post()
