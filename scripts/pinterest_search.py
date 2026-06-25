#!/usr/bin/env python3
import os
import sys
import json
import urllib.parse

# Ensure we can import ensure_playwright if needed
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def query_pinterest_search(query, limit=5):
    """
    Launches a headless Playwright browser to search Pinterest for inspiration.
    Extracts pin image URLs, titles, and details.
    """
    print(f"Querying Pinterest search for: '{query}'...")
    encoded_query = urllib.parse.quote(query)
    search_url = f"https://www.pinterest.com/search/pins/?q={encoded_query}"
    
    results = []
    
    # Try importing playwright
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed in the Python environment. Running setup first...")
        from render_newscard import ensure_playwright
        if not ensure_playwright():
            print("Failed to set up Playwright.")
            return results
        from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            # Launch chromium
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            # Go to pinterest search
            page.goto(search_url, timeout=45000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)  # Wait for dynamic grids to fully render
            
            # Find image tags
            img_tags = page.query_selector_all("img")
            
            seen_src = set()
            count = 0
            for img in img_tags:
                src = img.get_attribute("src")
                alt = img.get_attribute("alt") or ""
                
                # Check for standard Pinterest pin image URL subpaths
                if src and any(x in src for x in ["/236x/", "/474x/", "/564x/", "/736x/", "/originals/"]):
                    # Normalize to high-res 736x if possible
                    high_res_src = src.replace("/236x/", "/736x/").replace("/474x/", "/736x/").replace("/564x/", "/736x/")
                    if high_res_src not in seen_src:
                        seen_src.add(high_res_src)
                        
                        # Clean up alt text (often contains user names or hashtags)
                        title = alt.split(" - ")[0] if " - " in alt else alt
                        if not title:
                            title = f"Pinterest Inspiration Pin {count + 1}"
                            
                        results.append({
                            "title": title.strip(),
                            "image_url": high_res_src,
                            "pin_url": search_url
                        })
                        count += 1
                        if count >= limit:
                            break
                            
            browser.close()
    except Exception as e:
        print(f"Error querying Pinterest: {e}")
        
    return results

if __name__ == "__main__":
    search_term = sys.argv[1] if len(sys.argv) > 1 else "minimalist graphic card design layout"
    pins = query_pinterest_search(search_term)
    print(json.dumps(pins, indent=2))
