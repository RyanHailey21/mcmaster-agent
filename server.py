# ABOUTME: MCP server exposing McMaster-Carr product data.
# ABOUTME: Provides tools to search and lookup product information via web scraping.

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

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


def format_search_results(products: list) -> str:
    """Format search results as JSON."""
    results = []
    for p in products:
        results.append({
            "part_number": p.part_number,
            "name": p.name,
            "url": p.url
        })
    return json.dumps(results, indent=2)


# Create the MCP server
server = Server("mcmaster-carr")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="mcmaster_get_product",
            description="Get detailed product information from McMaster-Carr by part number. Returns name and 10-35+ specifications (material, size, pressure ratings, thread type, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "part_number": {
                        "type": "string",
                        "description": "McMaster-Carr part number (e.g., '47865K23', '2864N2')"
                    }
                },
                "required": ["part_number"]
            }
        ),
        Tool(
            name="mcmaster_search",
            description="Search McMaster-Carr and return product categories matching the query. Due to McMaster's JavaScript-heavy site, this returns category-level results. For specific products, you'll need a part number to use with mcmaster_get_product.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'ball valve', 'motorized actuator', 'brass fitting')"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="mcmaster_url",
            description="Generate a McMaster-Carr URL for a part number or search query without fetching data. Fast, no browser needed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "part_number": {
                        "type": "string",
                        "description": "McMaster-Carr part number"
                    },
                    "search_query": {
                        "type": "string",
                        "description": "Search query (alternative to part_number)"
                    }
                }
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "mcmaster_get_product":
            part_number = arguments.get("part_number", "").strip()
            if not part_number:
                return [TextContent(
                    type="text",
                    text="Error: part_number is required"
                )]

            product = await get_product_async(part_number)
            return [TextContent(
                type="text",
                text=format_product(product)
            )]

        elif name == "mcmaster_search":
            query = arguments.get("query", "").strip()
            if not query:
                return [TextContent(
                    type="text",
                    text="Error: query is required"
                )]

            products = await search_async(query)
            if not products:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "query": query,
                        "results": [],
                        "url": McMasterBrowser.get_search_url(query),
                        "note": "No products found. Try a different search term or open the URL directly."
                    }, indent=2)
                )]

            return [TextContent(
                type="text",
                text=json.dumps({
                    "query": query,
                    "count": len(products),
                    "results": [{"part_number": p.part_number, "name": p.name, "url": p.url} for p in products]
                }, indent=2)
            )]

        elif name == "mcmaster_url":
            part_number = arguments.get("part_number", "").strip()
            search_query = arguments.get("search_query", "").strip()

            if part_number:
                url = McMasterBrowser.get_product_url(part_number)
                return [TextContent(
                    type="text",
                    text=json.dumps({"url": url, "type": "product"}, indent=2)
                )]
            elif search_query:
                url = McMasterBrowser.get_search_url(search_query)
                return [TextContent(
                    type="text",
                    text=json.dumps({"url": url, "type": "search"}, indent=2)
                )]
            else:
                return [TextContent(
                    type="text",
                    text="Error: either part_number or search_query is required"
                )]

        else:
            return [TextContent(
                type="text",
                text=f"Unknown tool: {name}"
            )]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error: {str(e)}"
        )]


async def main_async():
    """Run the MCP server (async)."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    """Run the MCP server (sync entry point)."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
