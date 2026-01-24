# ABOUTME: Direct test of McMaster product page loading.
# ABOUTME: Dumps HTML content to analyze page structure.

import time
from seleniumbase import SB
from bs4 import BeautifulSoup

def test_direct():
    """Test product page and dump HTML."""
    print("Testing McMaster product page - dumping HTML...")

    part_number = "47865K23"
    url = f"https://www.mcmaster.com/{part_number}"

    print(f"\nURL: {url}")
    print("="*60)

    with SB(uc=True, headless=True, test=True) as sb:
        sb.activate_cdp_mode(url)
        time.sleep(5)

        html = sb.cdp.get_page_source()
        print(f"Total HTML length: {len(html)} chars")

        # Save HTML to file for analysis
        with open("/tmp/mcmaster_product.html", "w") as f:
            f.write(html)
        print(f"HTML saved to /tmp/mcmaster_product.html")

        # Parse and analyze
        soup = BeautifulSoup(html, 'html.parser')

        # Show first 5000 chars of body
        body = soup.find('body')
        if body:
            body_text = body.prettify()[:5000]
            print(f"\n--- First 5000 chars of body ---\n{body_text}")

        # Count unique class names
        print("\n\n--- Class analysis ---")
        class_counts = {}
        for elem in soup.find_all(class_=True):
            for cls in elem.get('class', []):
                class_counts[cls] = class_counts.get(cls, 0) + 1

        # Sort by count
        sorted_classes = sorted(class_counts.items(), key=lambda x: -x[1])
        print("Top 30 most common classes:")
        for cls, count in sorted_classes[:30]:
            print(f"  {cls}: {count}")

if __name__ == "__main__":
    test_direct()
