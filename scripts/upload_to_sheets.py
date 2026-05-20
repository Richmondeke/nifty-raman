#!/usr/bin/env python3
import os
import re
import glob
import json
import argparse
from datetime import datetime

# Try importing gspread, print a helpful error if not installed
try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("Error: Missing dependencies. Please run: pip install gspread google-auth")
    exit(1)

def parse_news_report(file_path):
    """
    Parses the markdown report file and returns a list of dictionaries representing deals.
    """
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split content by markdown horizontal rules (---)
    blocks = content.split("---")
    deals = []

    # Regex patterns
    title_pattern = re.compile(r"##\s+\d+\.\s+([^:]+):\s+(.+)")
    summary_pattern = re.compile(r"-\s+\*\*Summary\*\*:\s*(.+)")
    source_pattern = re.compile(r"-\s+\*\*Source\*\*:\s*\[([^\]]+)\]\(([^)]+)\)")
    keywords_pattern = re.compile(r"-\s+\*\*Keywords\*\*:\s*(.+)")
    score_pattern = re.compile(r"-\s+\*\*Score\*\*:\s*(.+)\s+\((\d)/5\)")

    date_str = os.path.basename(file_path)[:10]  # Extracts YYYY-MM-DD

    for block in blocks:
        block = block.strip()
        if not block.startswith("##"):
            continue

        # Extract title and info
        title_match = title_pattern.search(block)
        if not title_match:
            continue

        name_and_stage = title_match.group(1).strip()
        amount_stage = title_match.group(2).strip()

        # Split startup name and potential stage info if any
        # e.g., "Armada" and "$230 Million Series B"
        # Or parse it dynamically:
        startup_name = name_and_stage
        deal_size_stage = amount_stage

        summary_match = summary_pattern.search(block)
        summary = summary_match.group(1).strip() if summary_match else ""

        source_match = source_pattern.search(block)
        source_name = source_match.group(1).strip() if source_match else ""
        source_url = source_match.group(2).strip() if source_match else ""

        keywords_match = keywords_pattern.search(block)
        keywords = ""
        if keywords_match:
            # Clean up backticks
            keywords = keywords_match.group(1).replace("`", "").strip()

        score_match = score_pattern.search(block)
        score = score_match.group(2).strip() if score_match else ""

        deals.append({
            "Date": date_str,
            "Startup": startup_name,
            "Deal Details": deal_size_stage,
            "Summary": summary,
            "Source": source_name,
            "URL": source_url,
            "Keywords": keywords,
            "Score": score
        })

    return deals

def upload_to_sheets(deals, credentials_path, spreadsheet_name, sheet_name="Fundraising Deals"):
    """
    Authenticates and appends parsed deals to a Google Sheet.
    """
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    
    try:
        credentials = Credentials.from_service_account_file(credentials_path, scopes=scope)
        gc = gspread.authorize(credentials)
    except Exception as e:
        print(f"Authentication Error: Failed to load credentials from {credentials_path}. Details: {e}")
        return

    try:
        # Open the spreadsheet
        sh = gc.open(spreadsheet_name)
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"Error: Spreadsheet '{spreadsheet_name}' not found. Ensure it is shared with the Service Account email.")
        return

    try:
        # Get or create the worksheet
        worksheet = sh.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sh.add_worksheet(title=sheet_name, rows="100", cols="8")
        # Write headers
        headers = ["Date", "Startup", "Deal Details", "Summary", "Source URL", "Keywords", "Score"]
        worksheet.append_row(headers)
        print(f"Created new sheet: '{sheet_name}'")

    # Read existing URLs to prevent duplicates
    existing_urls = set(worksheet.col_values(5)[1:]) # Column 5 is URL

    rows_to_append = []
    for d in deals:
        if d["URL"] in existing_urls:
            print(f"Skipping duplicate: {d['Startup']} ({d['URL']})")
            continue
        
        rows_to_append.append([
            d["Date"],
            d["Startup"],
            d["Deal Details"],
            d["Summary"],
            d["URL"],
            d["Keywords"],
            d["Score"]
        ])

    if rows_to_append:
        worksheet.append_rows(rows_to_append)
        print(f"Successfully appended {len(rows_to_append)} new deals to '{spreadsheet_name}' under '{sheet_name}'.")
    else:
        print("No new deals to append.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload Daily Fundraising News to Google Sheets")
    parser.add_argument("--credentials", default="credentials.json", help="Path to Google Service Account credentials.json")
    parser.add_argument("--spreadsheet", required=True, help="Name of your Google Sheet")
    parser.add_argument("--sheet-name", default="Fundraising Deals", help="Tab name in the Google Sheet")
    parser.add_argument("--file", help="Path to specific news-report markdown file (defaults to latest)")

    args = parser.parse_args()

    # Locate report file
    report_file = args.file
    if not report_file:
        files = glob.glob("NewsReport/*-news-report.md")
        if not files:
            print("Error: No news report files found in NewsReport/")
            exit(1)
        report_file = max(files, key=os.path.getctime) # Latest file

    print(f"Parsing news report: {report_file}")
    parsed_deals = parse_news_report(report_file)
    
    if parsed_deals:
        print(f"Found {len(parsed_deals)} deals. Uploading to Sheets...")
        upload_to_sheets(parsed_deals, args.credentials, args.spreadsheet, args.sheet_name)
    else:
        print("No deals found to parse.")
