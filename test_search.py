# ABOUTME: Test script for McMaster browser search functionality.
# ABOUTME: Verifies that we can extract products from search results.

from urllib.parse import quote
from browser import McMasterBrowser

def test_search():
    """Test search functionality."""
    print("Testing McMaster browser search...")

    query = "ball valve 3/4"
    encoded = quote(query, safe='').replace('%20', '+')
    expected_url = f"https://www.mcmaster.com/{encoded}"
    print(f"Query: {query}")
    print(f"Expected URL: {expected_url}")

    with McMasterBrowser(headless=True) as browser:
        print("\nSearching...")
        state = browser.search(query)

        print(f"\nActual URL: {state.url}")
        print(f"Title: {state.title}")
        print(f"Page type: {state.page_type}")
        print(f"Products found: {len(state.products)}")

        if state.products:
            print("\nProducts extracted:")
            for i, p in enumerate(state.products[:15], 1):
                print(f"  {i}. {p.part_number}")

        # Also try a simpler search without slash
        print("\n\n--- Testing simpler search 'ball valve brass' ---")
        state2 = browser.search("ball valve brass")
        print(f"URL: {state2.url}")
        print(f"Title: {state2.title}")
        print(f"Page type: {state2.page_type}")
        print(f"Products found: {len(state2.products)}")

        if state2.products:
            print("\nProducts extracted:")
            for i, p in enumerate(state2.products[:15], 1):
                print(f"  {i}. {p.part_number}")

if __name__ == "__main__":
    test_search()
