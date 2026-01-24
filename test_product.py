# ABOUTME: Test script for McMaster product page navigation.
# ABOUTME: Tests product page detection and detail extraction.

import time
from browser import McMasterBrowser
from bs4 import BeautifulSoup

def test_product():
    """Test product page navigation and extraction."""
    print("Testing McMaster product page navigation...")

    # Test with a known working part number
    part_number = "47865K23"

    with McMasterBrowser(headless=False) as browser:  # headless=False to watch
        print(f"\n{'='*60}")
        print(f"Testing part number: {part_number}")
        print(f"{'='*60}")

        url = f"https://www.mcmaster.com/{part_number}"
        print(f"URL: {url}")

        # Use lower-level navigation for debugging
        browser._sb.activate_cdp_mode(url)
        browser._in_cdp_mode = True

        # Wait longer
        print("Waiting 5 seconds for page load...")
        time.sleep(5)

        # Get page info
        actual_url = browser._sb.get_current_url()
        print(f"Actual URL: {actual_url}")

        html = browser._sb.cdp.get_page_source()
        print(f"HTML length: {len(html)} chars")

        soup = BeautifulSoup(html, 'html.parser')

        # Get title
        title = soup.find('title')
        print(f"Title: {title.get_text() if title else '(none)'}")

        # Look for spec table
        print("\nLooking for spec-related elements...")
        spec_found = False
        for elem in soup.find_all(class_=True):
            classes = ' '.join(elem.get('class', []))
            if 'spec' in classes.lower():
                print(f"  Found: {classes[:80]}...")
                spec_found = True
                if len(list(elem.children)) > 0:
                    print(f"    Has {len(list(elem.children))} children")
                    first_child = list(elem.children)[0]
                    if hasattr(first_child, 'get_text'):
                        text = first_child.get_text()[:100]
                        print(f"    First child text: {text}")

        if not spec_found:
            print("  No spec elements found!")

            # Look for any element with substantial content
            print("\nLooking for any content indicators...")
            for tag in ['h1', 'h2', 'h3']:
                headers = soup.find_all(tag)
                if headers:
                    print(f"  {tag} tags: {len(headers)}")
                    for h in headers[:3]:
                        text = h.get_text(strip=True)[:60]
                        if text:
                            print(f"    '{text}'")

        # Check for iframes
        iframes = soup.find_all('iframe')
        print(f"\nIframes found: {len(iframes)}")

        # Check for any error messages
        for elem in soup.find_all(string=True):
            text = str(elem).strip()
            if 'error' in text.lower() or 'not found' in text.lower():
                if len(text) < 200:
                    print(f"  Potential error: {text}")

if __name__ == "__main__":
    test_product()
