import os
import sys
import yaml
import json
import logging
import datetime
import random
from pathlib import Path

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Google Gemini API (new SDK)
from google import genai
from google.genai import types

# SendGrid for email
import smtplib
from email.message import EmailMessage


# Load configuration
CONFIG_PATH = Path(__file__).parent / "config.yaml"
if not CONFIG_PATH.exists():
    sys.exit(f"Configuration file not found: {CONFIG_PATH}")

with open(CONFIG_PATH, "r") as f:
    cfg = yaml.safe_load(f)

# Setup logging
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / f"newsletter_{datetime.date.today()}.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# Helper: rotate Gemini API keys
def get_gemini_key():
    # Prefer environment variable; fallback to config file keys
    keys_str = os.getenv("GEMINI_KEYS")
    if keys_str:
        keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    else:
        keys = cfg.get("gemini_keys", [])
    if not keys:
        raise RuntimeError("No Gemini API keys available")
    # Simple round‑robin based on day of month
    index = datetime.date.today().day % len(keys)
    return keys[index]

# Ordered list of models to try (best → fastest)
GEMINI_MODELS = ["gemini-3.5-flash", "gemini-3-flash-preview", "gemini-3-pro-preview", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]

def get_all_gemini_keys():
    """Return all available Gemini API keys."""
    keys_str = os.getenv("GEMINI_KEYS")
    if keys_str:
        keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    else:
        keys = cfg.get("gemini_keys", [])
    if not keys:
        raise RuntimeError("No Gemini API keys available")
    return keys

ALL_GEMINI_KEYS = get_all_gemini_keys()

def generate_with_fallback(prompt):
    """Try every key × every model until one succeeds. Returns text or raises."""
    import time
    for model_name in GEMINI_MODELS:
        for key_index, key in enumerate(ALL_GEMINI_KEYS):
            try:
                client = genai.Client(api_key=key)
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                print(f"      ↳ OK with {model_name} / key[{key_index}]")
                return response.text.strip()
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    print(f"      ↳ quota hit {model_name} / key[{key_index}] — trying next...")
                    time.sleep(1)
                    continue
                else:
                    # Non-quota error — log and skip to next model
                    print(f"      ↳ error {model_name} / key[{key_index}]: {e}")
                    break
    raise RuntimeError(f"All models and keys exhausted for prompt.")

# Load briefs (supports local JSON file or remote URL)
def load_briefs(source):
    if source.startswith("http://") or source.startswith("https://"):
        resp = requests.get(source)
        resp.raise_for_status()
        return resp.json()
    else:
        with open(source, "r") as f:
            return json.load(f)

briefs = load_briefs(cfg.get("briefs_source", "briefs.json"))

# Load YouTube recommendations (list of dicts with title and url)
def load_youtube(path):
    if not path:
        return []
    if path.startswith("http"):
        resp = requests.get(path)
        resp.raise_for_status()
        return resp.json()
    else:
        with open(path, "r") as f:
            return json.load(f)

youtube_recs = load_youtube(cfg.get("youtube_recommendations", "youtube_recommendations.json"))

# Generate section copy using Gemini
CATEGORIES = ["TV", "Film", "Games", "Ads"]
sections = {}
failed_sections = []
for cat in CATEGORIES:
    import time
    # Filter briefs for this category
    cat_briefs = [b for b in briefs if b.get("category", "").lower() == cat.lower()]
    if not cat_briefs:
        sections[cat] = "No current opportunities."
        print(f"  [{cat}] No briefs found — skipping AI generation.")
        continue
    # Prepare prompt
    prompt = (
        f"Write a concise, enthusiastic briefing for sync licensing opportunities in {cat}. "
        f"Include up to three top briefs with title and a one-sentence description. "
        f"Use a friendly tone for artists."
        f"\nBriefs data: {json.dumps(cat_briefs[:3])}"
    )
    print(f"  [{cat}] Generating content...")
    try:
        text = generate_with_fallback(prompt)
        sections[cat] = text
        print(f"  [{cat}] ✅ Generated ({len(text)} chars)")
        logging.info(f"Content generated for {cat}")
    except Exception as e:
        logging.error(f"Gemini generation failed for {cat}: {e}")
        print(f"  [{cat}] ❌ FAILED: {e}")
        sections[cat] = None
        failed_sections.append(cat)
    # Small pause to respect per-minute rate limits
    time.sleep(2)

# ── Pre-send validation ──────────────────────────────────────────────────────
if failed_sections:
    msg = f"Aborting: Gemini failed to generate content for sections: {', '.join(failed_sections)}. Newsletter NOT sent."
    logging.error(msg)
    print(f"\n🚫 {msg}")
    sys.exit(1)

print(f"\n✅ All {len([s for s in sections if sections[s] != 'No current opportunities.'])} sections generated successfully. Proceeding to send...")

# Choose a few YouTube videos (random sample up to 2)
selected_videos = random.sample(youtube_recs, min(2, len(youtube_recs))) if youtube_recs else []

# Render email using Jinja2 template
env = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    autoescape=select_autoescape(['html', 'xml'])
)
template = env.get_template('email_template.html')
html_content = template.render(
    subject=cfg.get("subject", "Sync Licensing Newsletter"),
    sections=sections,
    videos=selected_videos,
    sender=cfg.get("sender_email"),
    date=datetime.date.today().strftime("%B %d, %Y")
)

# Load recipients (CSV expected: email,name)
recipients_path = Path(__file__).parent / cfg.get("recipients_csv", "recipients.csv")
if not recipients_path.exists():
    logging.error(f"Recipients file not found: {recipients_path}")
    sys.exit(1)

recipients = []
with open(recipients_path, "r") as f:
    for line in f:
        email, name = line.strip().split(",")
        recipients.append({"email": email.strip(), "name": name.strip()})

gmail_user = cfg.get("gmail_user")

gmail_app_password = cfg.get("gmail_app_password")

if not gmail_user or not gmail_app_password:
    logging.error("Gmail credentials not provided")
    sys.exit(1)

# Send emails via Gmail SMTP
with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
    smtp.login(gmail_user, gmail_app_password)
    for rec in recipients:
        msg = EmailMessage()
        msg['Subject'] = cfg.get('subject', 'Sync Licensing Newsletter')
        msg['From'] = cfg.get('sender_email')
        msg['To'] = rec['email']
        msg.set_content('This is an HTML email', subtype='html')
        msg.add_alternative(html_content, subtype='html')
        try:
            smtp.send_message(msg)
            logging.info(f"Sent newsletter to {rec['email']}")
        except Exception as e:
            logging.error(f"Failed to send to {rec['email']}: {e}")

print("Newsletter generation and dispatch completed.")
