# ABOUTME: MCP server exposing McMaster-Carr product data.
# ABOUTME: Provides tools to search and lookup product information via web scraping.

import asyncio
import atexit
import json
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Optional

# SeleniumBase creates and clears ./downloaded_files during browser startup.
# Give each server process its own writable directory before importing it.
_original_working_dir = Path.cwd()
_working_dir = tempfile.TemporaryDirectory(prefix="mcmaster-mcp-", ignore_cleanup_errors=True)
os.chdir(_working_dir.name)
atexit.register(os.chdir, _original_working_dir)

from mcp.server.mcpserver import MCPServer

from browser import McMasterBrowser, ProductDetails


# Worker pool: each worker thread owns one visible browser with its own profile slot (see browser.py), so up to
# MCMASTER_WORKERS calls run in parallel. Calls beyond that queue. A worker's browser is started on its first call
# and reused after that (it keeps the session and cookies). Set MCMASTER_WORKERS=1 for the old one-browser behaviour.
WORKERS = max(1, int(os.environ.get("MCMASTER_WORKERS", "3")))
_executor = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="mcmaster-worker")
_local = threading.local()
_browsers: list = []
_browsers_lock = threading.Lock()


def get_browser() -> McMasterBrowser:
    """This worker thread's browser, started on first use. Visible, since McMaster blocks headless browsers.

    A browser whose window was closed or whose Chrome crashed is discarded and a fresh one started, so the worker
    does not fail every later call until the server restarts.
    """
    browser = getattr(_local, "browser", None)
    if browser is not None and not browser.is_alive():
        _discard_browser(browser)
        browser = None
    if browser is None:
        browser = McMasterBrowser(headless=False)
        browser.start()
        _local.browser = browser
        with _browsers_lock:
            _browsers.append(browser)
    return browser


def _discard_browser(browser) -> None:
    """Stop this worker's (dead) browser and forget it, releasing its profile slot."""
    try:
        browser.stop()
    except Exception:
        pass
    with _browsers_lock:
        if browser in _browsers:
            _browsers.remove(browser)
    if getattr(_local, "browser", None) is browser:
        _local.browser = None


def _with_browser(action):
    """Run action(browser) on this worker's browser. If it fails because the browser died (window closed, Chrome
    crashed), retry once on a fresh browser; any other error is raised unchanged."""
    browser = get_browser()
    try:
        return action(browser)
    except Exception:
        if browser.is_alive():
            raise
        _discard_browser(browser)
    return action(get_browser())


def _stop_browsers():
    with _browsers_lock:
        for b in _browsers:
            b.stop()
        _browsers.clear()


atexit.register(_stop_browsers)


def _get_product_sync(part_number: str) -> ProductDetails:
    """Sync wrapper for get_product."""
    return _with_browser(lambda browser: browser.get_product(part_number))


def _search_sync(query: str) -> list:
    """Sync wrapper for search."""
    return _with_browser(lambda browser: browser.search(query).products)


async def get_product_async(part_number: str) -> ProductDetails:
    """Async wrapper using thread executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _get_product_sync, part_number)


async def search_async(query: str) -> list:
    """Async wrapper for search."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _search_sync, query)


def _download_cad_sync(part_number: str, file_format: str, output_dir: Optional[str]) -> dict:
    """Sync wrapper for download_cad."""
    destination = Path(output_dir) if output_dir else Path("downloads")
    if not destination.is_absolute():
        destination = _original_working_dir / destination
    return _with_browser(
        lambda browser: browser.download_cad(part_number, file_format=file_format, output_dir=str(destination))
    )


async def download_cad_async(part_number: str, file_format: str = "3-D STEP", output_dir: Optional[str] = None) -> dict:
    """Async wrapper for download_cad."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _download_cad_sync, part_number, file_format, output_dir)


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



@server.tool(
    name="mcmaster_download_cad",
    description="Download authentic 3D CAD model (STEP, SolidWorks, IGES, SAT) or 2D drawing (DWG, DXF, PDF) directly from McMaster-Carr to disk.",
)
async def mcmaster_download_cad(
    part_number: str,
    file_format: str = "3-D STEP",
    output_dir: Optional[str] = None,
) -> str:
    """Download authentic CAD models from McMaster-Carr.

    Args:
        part_number: McMaster-Carr part number (e.g., '91290A115', '9414T11', '1497K24')
        file_format: CAD format: '3-D STEP' (default), '3-D SolidWorks', '3-D IGES', '3-D SAT', '2-D DWG', '2-D DXF', '2-D PDF'
        output_dir: Target directory path to save the CAD file (defaults to ./downloads)
    """
    part_num = part_number.strip()
    if not part_num:
        return json.dumps({"success": False, "error": "part_number is required"}, indent=2)

    try:
        res = await download_cad_async(part_num, file_format, output_dir)
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e), "part_number": part_num}, indent=2)


def main():
    """Run the MCP server (sync entry point)."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
