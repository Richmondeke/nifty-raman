#!/usr/bin/env python3
import os
import sys
import json
import time
import requests
import urllib.parse
from datetime import datetime
from flask import Flask, request, redirect, jsonify, render_template, send_from_directory

# File paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
IMAGES_DIR = os.path.join(PROJECT_ROOT, "NewsReport", "images")
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "templates")

if os.environ.get("VERCEL") == "1":
    # On Vercel, the filesystem is read-only. Store files in /tmp so writes succeed
    TOKEN_FILE = "/tmp/linkedin_tokens.json"
    QUEUE_FILE = "/tmp/scheduled_posts.json"
    CHANNELS_FILE = "/tmp/connected_channels.json"
    
    # Pre-load queue and channels from project files if /tmp versions do not exist yet
    src_queue = os.path.join(PROJECT_ROOT, "scheduled_posts.json")
    if not os.path.exists(QUEUE_FILE) and os.path.exists(src_queue):
        try:
            import shutil
            shutil.copy2(src_queue, QUEUE_FILE)
        except Exception:
            pass
            
    src_channels = os.path.join(PROJECT_ROOT, "connected_channels.json")
    if not os.path.exists(CHANNELS_FILE) and os.path.exists(src_channels):
        try:
            import shutil
            shutil.copy2(src_channels, CHANNELS_FILE)
        except Exception:
            pass
            
    src_tokens = os.path.join(PROJECT_ROOT, "linkedin_tokens.json")
    if not os.path.exists(TOKEN_FILE) and os.path.exists(src_tokens):
        try:
            import shutil
            shutil.copy2(src_tokens, TOKEN_FILE)
        except Exception:
            pass
else:
    TOKEN_FILE = os.path.join(PROJECT_ROOT, "linkedin_tokens.json")
    QUEUE_FILE = os.path.join(PROJECT_ROOT, "scheduled_posts.json")
    CHANNELS_FILE = os.path.join(PROJECT_ROOT, "connected_channels.json")

# Credentials defaults
CLIENT_ID = "78k2fun9a7snlf"
CLIENT_SECRET = "WPL_AP1.cxSG0AoKdqHo0MD3.AKSBxA=="
REDIRECT_URI = "http://localhost:8080/callback"
SCOPES = "w_member_social w_organization_social rw_organization_admin"

# Load customized credentials from .env if present
env_path = os.path.join(PROJECT_ROOT, ".env")
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line_strip = line.strip()
            if not line_strip or line_strip.startswith("#"):
                continue
            if "=" in line_strip:
                key, val = line_strip.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key == "LINKEDIN_CLIENT_ID":
                    CLIENT_ID = val
                elif key == "LINKEDIN_CLIENT_SECRET":
                    CLIENT_SECRET = val
                elif key == "LINKEDIN_REDIRECT_URI":
                    REDIRECT_URI = val
                elif key == "LINKEDIN_SCOPES":
                    SCOPES = val

app = Flask(__name__, template_folder=TEMPLATE_DIR)

# Load existing configurations/tokens
def load_tokens():
    # Try loading access token from environment variables (secure Vercel method)
    env_token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    if env_token:
        return {"access_token": env_token}
        
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_tokens(tokens):
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)

def load_queue():
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_queue(queue):
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)

# Helper function to query user profile / organizations
def get_linkedin_pages(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # 1. Fetch organizations where the user is an administrator
    url = "https://api.linkedin.com/v2/organizationalEntityAcls?q=roleAssignee&role=ADMINISTRATOR"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            elements = data.get("elements", [])
            pages = []
            for el in elements:
                org_urn = el.get("organizationalEntity")
                if org_urn:
                    # Fetch organization details
                    org_id = org_urn.split(":")[-1]
                    details_url = f"https://api.linkedin.com/v2/organizations/{org_id}"
                    org_r = requests.get(details_url, headers=headers, timeout=10)
                    if org_r.status_code == 200:
                        org_data = org_r.json()
                        pages.append({
                            "urn": org_urn,
                            "name": org_data.get("localizedName", f"Organization {org_id}"),
                            "vanity_name": org_data.get("vanityName", "")
                        })
            return pages
    except Exception as e:
        print(f"Error fetching pages: {e}")
    return []

# Helper function to upload image and publish post on LinkedIn
def publish_to_linkedin(access_token, org_urn, text, image_path=None):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }
    
    media_urn = None
    if image_path and os.path.exists(image_path):
        # Step 1: Register Upload
        register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
        payload = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": org_urn,
                "supportedUploadMechanisms": ["SYNCHRONOUS_UPLOAD"]
            }
        }
        try:
            r = requests.post(register_url, headers=headers, json=payload, timeout=15)
            if r.status_code == 200:
                data = r.json()
                upload_url = data["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadMechanism"]["uploadUrl"]
                media_urn = data["value"]["asset"]
                
                # Step 2: Upload Binary
                with open(image_path, "rb") as img_file:
                    put_headers = {"Authorization": f"Bearer {access_token}"}
                    upload_r = requests.put(upload_url, headers=put_headers, data=img_file, timeout=30)
                    if upload_r.status_code != 201 and upload_r.status_code != 200:
                        print(f"Failed to upload binary: {upload_r.text}")
                        media_urn = None
            else:
                print(f"Failed to register upload: {r.text}")
        except Exception as e:
            print(f"Exception during upload: {e}")
            media_urn = None
            
    # Step 3: Create Share Post
    post_url = "https://api.linkedin.com/v2/posts"
    post_payload = {
        "author": org_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": []
        },
        "lifecycleState": "PUBLISHED"
    }
    
    if media_urn:
        post_payload["content"] = {
            "media": {
                "title": "Briefing Showcase",
                "id": media_urn
            }
        }
        
    try:
        r = requests.post(post_url, headers=headers, json=post_payload, timeout=15)
        if r.status_code == 201:
            post_urn = r.headers.get("x-restli-id", "success")
            return True, post_urn
        else:
            return False, r.text
    except Exception as e:
        return False, str(e)

# Exposing static images
@app.route('/images/<path:filename>')
def get_image(filename):
    return send_from_directory(IMAGES_DIR, filename)

@app.route('/')
def index():
    tokens = load_tokens()
    has_token = "access_token" in tokens
    
    pages = []
    if has_token:
        pages = get_linkedin_pages(tokens["access_token"])
        
    # Get all image briefing cards (showcase briefing/lifestyle/spotlight/etc.)
    images = []
    if os.path.exists(IMAGES_DIR):
        for f in os.listdir(IMAGES_DIR):
            if f.endswith((".jpg", ".png")) and not f.endswith("-scraped.jpg"):
                label = f.replace("showcase_", "").replace(".jpg", "").replace(".png", "").replace("-card", "").replace("_", " ").replace("-", " ").title()
                images.append({"filename": f, "label": label})
                
    queue = load_queue()
    # Sort queue: pending first, then by date desc
    queue.sort(key=lambda x: (x.get("status") != "pending", x.get("time")))
    
    return render_template(
        "linkedin_dashboard.html",
        has_token=has_token,
        pages=pages,
        images=images,
        queue=queue
    )

@app.route('/login')
def login():
    auth_url = (
        f"https://www.linkedin.com/oauth/v2/authorization?"
        f"response_type=code&client_id={CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&scope={urllib.parse.quote(SCOPES)}"
    )
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get("code")
    if not code:
        return "Authorization failed: no code provided.", 400
        
    token_url = "https://www.linkedin.com/oauth/v2/accessToken"
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    
    try:
        r = requests.post(token_url, data=payload, timeout=15)
        if r.status_code == 200:
            data = r.json()
            save_tokens(data)
            return redirect('/')
        else:
            return f"Failed to exchange token: {r.text}", 400
    except Exception as e:
        return f"Token exchange failed: {e}", 500

@app.route('/schedule', methods=['POST'])
def schedule_post():
    page_urn = request.form.get("page_urn")
    image_filename = request.form.get("image_filename")
    commentary = request.form.get("commentary")
    scheduled_time = request.form.get("scheduled_time")
    
    if not page_urn or not commentary or not scheduled_time:
        return "Missing fields", 400
        
    page_name = "Company Page"
    if page_urn == "stub_x":
        if os.path.exists(CHANNELS_FILE):
            try:
                with open(CHANNELS_FILE, "r") as f:
                    data = json.load(f)
                    page_name = data.get("x", {}).get("name", "Twitter / X")
            except Exception:
                page_name = "Twitter / X"
    elif page_urn == "stub_meta":
        if os.path.exists(CHANNELS_FILE):
            try:
                with open(CHANNELS_FILE, "r") as f:
                    data = json.load(f)
                    page_name = data.get("meta", {}).get("name", "Meta Page")
            except Exception:
                page_name = "Meta Page"
    else:
        tokens = load_tokens()
        pages = get_linkedin_pages(tokens.get("access_token", ""))
        page_name = next((p["name"] for p in pages if p["urn"] == page_urn), "LinkedIn Page")
    
    queue = load_queue()
    post_id = str(int(time.time() * 1000))
    queue.append({
        "id": post_id,
        "page_urn": page_urn,
        "page_name": page_name,
        "image": image_filename if image_filename else None,
        "commentary": commentary,
        "time": scheduled_time,
        "status": "pending"
    })
    save_queue(queue)
    return redirect('/')

@app.route('/publish-now/<post_id>', methods=['POST'])
def publish_now(post_id):
    queue = load_queue()
    post = next((p for p in queue if p["id"] == post_id), None)
    if not post:
        return jsonify({"success": False, "error": "Post not found"}), 404
        
    # Check if this is a dummy simulated channel
    if post.get("page_urn") in ["stub_x", "stub_meta"]:
        post["status"] = "published"
        post["published_urn"] = f"urn:li:simulated:{post['page_urn']}:{post_id}"
        save_queue(queue)
        return jsonify({"success": True})
        
    tokens = load_tokens()
    access_token = tokens.get("access_token")
    if not access_token:
        return jsonify({"success": False, "error": "LinkedIn not connected"}), 401
        
    image_path = None
    if post.get("image"):
        image_path = os.path.join(IMAGES_DIR, post["image"])
        
    success, res = publish_to_linkedin(
        access_token,
        post["page_urn"],
        post["commentary"],
        image_path
    )
    
    if success:
        post["status"] = "published"
        post["published_urn"] = res
        save_queue(queue)
        return jsonify({"success": True})
    else:
        post["status"] = "failed"
        post["error"] = res
        save_queue(queue)
        return jsonify({"success": False, "error": res})

@app.route('/delete-post/<post_id>', methods=['POST'])
def delete_post(post_id):
    queue = load_queue()
    queue = [p for p in queue if p["id"] != post_id]
    save_queue(queue)
    return jsonify({"success": True})

# Dynamic settings for X/Meta simulated credentials
@app.route('/connect-channel', methods=['POST'])
def connect_channel():
    data = request.json or {}
    channel = data.get("channel")
    name = data.get("name")
    secret = data.get("secret")
    
    if not channel or not name:
        return jsonify({"success": False, "error": "Missing channel or handle name"}), 400
        
    connected = {}
    if os.path.exists(CHANNELS_FILE):
        try:
            with open(CHANNELS_FILE, "r") as f:
                connected = json.load(f)
        except Exception:
            pass
            
    connected[channel] = {
        "connected": True,
        "name": name,
        "secret": secret
    }
    
    try:
        with open(CHANNELS_FILE, "w") as f:
            json.dump(connected, f, indent=2)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/get-channels-status')
def get_channels_status():
    if os.path.exists(CHANNELS_FILE):
        try:
            with open(CHANNELS_FILE, "r") as f:
                return jsonify(json.load(f))
        except Exception:
            pass
    return jsonify({
        "x": {"connected": False},
        "meta": {"connected": False}
    })

@app.route('/reschedule-post', methods=['POST'])
def reschedule_post():
    data = request.json or {}
    post_id = data.get("id")
    new_time = data.get("time")
    
    if not post_id or not new_time:
        return jsonify({"success": False, "error": "Missing parameters"}), 400
        
    queue = load_queue()
    for post in queue:
        if post["id"] == post_id:
            post["time"] = new_time
            save_queue(queue)
            return jsonify({"success": True})
            
    return jsonify({"success": False, "error": "Post not found"}), 404

# Periodic Publisher (to be called by local scheduler / cron)
def run_publisher_cron():
    print("Running publisher check...")
    queue = load_queue()
    tokens = load_tokens()
    access_token = tokens.get("access_token")
    
    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M")
    any_published = False
    
    for post in queue:
        if post["status"] == "pending" and post["time"] <= now_str:
            print(f"Time matches! Publishing post {post['id']}...")
            
            # Simulated channels
            if post.get("page_urn") in ["stub_x", "stub_meta"]:
                post["status"] = "published"
                post["published_urn"] = f"urn:li:simulated:{post['page_urn']}:{post['id']}"
                print(f"Published simulated post successfully.")
                any_published = True
                continue
                
            if not access_token:
                print("LinkedIn not connected. Skipping LinkedIn post.")
                post["status"] = "failed"
                post["error"] = "LinkedIn access token is missing."
                any_published = True
                continue
                
            image_path = None
            if post.get("image"):
                image_path = os.path.join(IMAGES_DIR, post["image"])
                
            success, res = publish_to_linkedin(
                access_token,
                post["page_urn"],
                post["commentary"],
                image_path
            )
            if success:
                post["status"] = "published"
                post["published_urn"] = res
                print(f"Published successfully URN: {res}")
            else:
                post["status"] = "failed"
                post["error"] = res
                print(f"Failed to publish: {res}")
            any_published = True
            
    if any_published:
        save_queue(queue)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "cron":
        run_publisher_cron()
    else:
        # Parse port from REDIRECT_URI dynamically
        port = 8080
        try:
            parsed_url = urllib.parse.urlparse(REDIRECT_URI)
            if parsed_url.port:
                port = parsed_url.port
        except Exception:
            pass
        print(f"Starting Multi-Channel Scheduling Dashboard on http://localhost:{port}...")
        app.run(host="0.0.0.0", port=port)
