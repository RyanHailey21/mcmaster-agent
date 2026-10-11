# ABOUTME: MCP server exposing McMaster-Carr product data.
# ABOUTME: Provides tools to search and lookup product information via web scraping.

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import Optional

from mcp.server.mcpserver import MCPServer

from browser import McMasterBrowser, ProductDetails


# Thread pool for running sync browser operations
_executor = ThreadPoolExecutor(max_workers=1)

# Global browser instance (reuses session and cookies)
_browser: Optional[McMasterBrowser] = None


def get_browser() -> McMasterBrowser:
    """Get or create the McMaster browser. Uses visible browser since McMaster blocks headless."""
    global _browser
    if _browser is None:
        _browser = McMasterBrowser(headless=False)
        _browser.start()
    return _browser


def _get_product_sync(part_number: str) -> ProductDetails:
    """Sync wrapper for get_product."""
    browser = get_browser()
    return browser.get_product(part_number)


def _search_sync(query: str) -> list:
    """Sync wrapper for search."""
    browser = get_browser()
    state = browser.search(query)
    return state.products


async def get_product_async(part_number: str) -> ProductDetails:
    """Async wrapper using thread executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _get_product_sync, part_number)


async def search_async(query: str) -> list:
    """Async wrapper for search."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _search_sync, query)


def format_product(product: ProductDetails) -> str:
    """Format product info as JSON."""
    data = asdict(product)
    # Remove None values and empty dicts
    data = {k: v for k, v in data.items() if v is not None and v != {}}
    return json.dumps(data, indent=2)


# Create the MCP server
server = MCPServer("mcmaster-carr")


@server.tool(
    name="mcmaster_get_product",
    description="Get detailed product information from McMaster-Carr by part number. Returns name and 10-35+ specifications (material, size, pressure ratings, thread type, etc.).",
)
async def mcmaster_get_product(part_number: str) -> str:
    """Get detailed product information from McMaster-Carr by part number.

    Args:
        part_number: McMaster-Carr part number (e.g., '47865K23', '2864N2')
    """
    part_num = part_number.strip()
    if not part_num:
        return "Error: part_number is required"

    try:
        product = await get_product_async(part_num)
        return format_product(product)
    except Exception as e:
        return f"Error: {str(e)}"


@server.tool(
    name="mcmaster_search",
    description="Search McMaster-Carr and return product categories matching the query. Due to McMaster's JavaScript-heavy site, this returns category-level results. For specific products, you'll need a part number to use with mcmaster_get_product.",
)
async def mcmaster_search(query: str) -> str:
    """Search McMaster-Carr and return product categories/results matching query.

    Args:
        query: Search query (e.g., 'ball valve', 'motorized actuator', 'brass fitting')
    """
    q = query.strip()
    if not q:
        return "Error: query is required"

    try:
        products = await search_async(q)
        if not products:
            return json.dumps(
                {
                    "query": q,
                    "results": [],
                    "url": McMasterBrowser.get_search_url(q),
                    "note": "No products found. Try a different search term or open the URL directly.",
                },
                indent=2,
            )

        return json.dumps(
            {
                "query": q,
                "count": len(products),
                "results": [
                    {"part_number": p.part_number, "name": p.name, "url": p.url}
                    for p in products
                ],
            },
            indent=2,
        )
    except Exception as e:
        return f"Error: {str(e)}"


@server.tool(
    name="mcmaster_url",
    description="Generate a McMaster-Carr URL for a part number or search query without fetching data. Fast, no browser needed.",
)
def mcmaster_url(part_number: Optional[str] = None, search_query: Optional[str] = None) -> str:
    """Generate a McMaster-Carr URL for a part number or search query without fetching data.

    Args:
        part_number: McMaster-Carr part number
        search_query: Search query (alternative to part_number)
    """
    pn = (part_number or "").strip()
    sq = (search_query or "").strip()

    if pn:
        url = McMasterBrowser.get_product_url(pn)
        return json.dumps({"url": url, "type": "product"}, indent=2)
    elif sq:
        url = McMasterBrowser.get_search_url(sq)
        return json.dumps({"url": url, "type": "search"}, indent=2)
    else:
        return "Error: either part_number or search_query is required"


def main():
    """Run the MCP server (sync entry point)."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
