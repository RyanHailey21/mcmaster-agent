# ABOUTME: Test JavaScript extraction for McMaster product data.
# ABOUTME: Extracts product info from image URLs and window objects.

import time
import json
import re
from seleniumbase import SB

def test_js_extraction():
    """Extract product data via JavaScript."""
    print("Testing JavaScript extraction...")

    with SB(uc=True, headless=True, test=True) as sb:
        # Navigate to search page
        print("\nNavigating to ball valve search...")
        sb.activate_cdp_mode("https://www.mcmaster.com/ball+valve+3/4")
        time.sleep(8)

        # Extract part numbers from all image URLs in performance log
        print("\nExtracting part numbers from loaded images...")
        parts_from_images = sb.cdp.evaluate('''
            (function() {
                let entries = performance.getEntriesByType('resource');
                let parts = [];
                for (let e of entries) {
                    // McMaster part numbers: digits, letters, digits (e.g., 47865K23)
                    let matches = e.name.match(/\\/([0-9]+[a-zA-Z]+[0-9]+)/g);
                    if (matches) {
                        for (let m of matches) {
                            let part = m.substring(1).toUpperCase(); // Remove leading slash
                            if (/^[0-9]+[A-Z]+[0-9]+$/.test(part)) {
                                parts.push(part);
                            }
                        }
                    }
                }
                // Dedupe
                return [...new Set(parts)];
            })()
        ''')
        print(f"Found {len(parts_from_images)} unique part numbers from images:")
        for part in parts_from_images[:20]:
            print(f"  {part}")

        # Get the full HTML and look for part numbers
        print("\n\nExtracting part numbers from page source...")
        html = sb.cdp.get_page_source()
        # Part number pattern
        all_parts = set(re.findall(r'\b(\d+[A-Z]+\d+)\b', html))
        print(f"Found {len(all_parts)} unique part numbers in HTML:")
        for part in list(all_parts)[:20]:
            print(f"  {part}")

        # Try to get product names from McMaster's React objects
        print("\n\nExploring McMaster React objects for product data...")
        react_data = sb.cdp.evaluate('''
            (function() {
                let results = {};

                // Check SpecSearchPopoutManager
                if (window.SpecSearchPopoutManager) {
                    results.SpecSearchPopoutManager = {
                        keys: Object.keys(window.SpecSearchPopoutManager),
                        prototype: Object.getOwnPropertyNames(window.SpecSearchPopoutManager.prototype || {})
                    };
                }

                // Check SpecIndustrialInfoManager
                if (window.SpecIndustrialInfoManager) {
                    results.SpecIndustrialInfoManager = {
                        keys: Object.keys(window.SpecIndustrialInfoManager),
                        INFO_TYPES: window.SpecIndustrialInfoManager.INFO_TYPES
                    };
                }

                // Check McMasterReact
                if (window.McMasterReact) {
                    results.McMasterReact = {
                        keys: Object.keys(window.McMasterReact)
                    };
                    // Check if there's spec search data
                    if (window.McMasterReact.SpecSearch) {
                        results.SpecSearch = Object.keys(window.McMasterReact.SpecSearch);
                    }
                }

                // Check McMaster.Redux if it exists
                if (window.McMaster && window.McMaster.Redux) {
                    results.Redux = Object.keys(window.McMaster.Redux);
                }

                return results;
            })()
        ''')
        print(json.dumps(react_data, indent=2))

        # Now let's try to directly scrape any visible product info
        print("\n\nLooking for visible product elements in DOM...")
        visible_products = sb.cdp.evaluate('''
            (function() {
                let products = [];

                // Look for any elements that might contain product info
                // McMaster uses various class patterns

                // Try to find elements with product-related text
                let allElements = document.querySelectorAll('*');
                for (let el of allElements) {
                    // Skip if inside iframe
                    if (el.closest('iframe')) continue;

                    let text = el.textContent || '';
                    // Look for part number pattern in text
                    let match = text.match(/^([0-9]+[A-Z]+[0-9]+)$/);
                    if (match && text.length < 20) {
                        products.push({
                            tag: el.tagName,
                            partNumber: match[1],
                            classes: el.className
                        });
                    }
                }

                // Dedupe by part number
                let seen = new Set();
                return products.filter(p => {
                    if (seen.has(p.partNumber)) return false;
                    seen.add(p.partNumber);
                    return true;
                });
            })()
        ''')
        print(f"Found {len(visible_products)} visible product elements:")
        for p in visible_products[:10]:
            print(f"  {p.get('partNumber')} ({p.get('tag')})")

        # Final summary - we can use the part numbers from images to fetch product details
        if parts_from_images:
            print(f"\n\n=== SUMMARY ===")
            print(f"Successfully found {len(parts_from_images)} product part numbers from search results.")
            print("These can be used to fetch full product details via mcmaster_get_product tool.")
            print("\nPart numbers found:")
            for part in parts_from_images[:10]:
                print(f"  - {part}")

if __name__ == "__main__":
    test_js_extraction()
