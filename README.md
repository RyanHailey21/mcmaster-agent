# ABOUTME: Documentation for McMaster-Carr MCP server.
# ABOUTME: Covers installation, configuration, and usage.

# McMaster-Carr MCP Server

MCP server for searching and looking up product information from McMaster-Carr.

Uses SeleniumBase UC mode to extract product data from JavaScript-rendered pages.

## Features

- **CAD Model Download**: Download authentic 3D CAD models (STEP, SolidWorks, IGES, SAT) and 2D drawings directly to disk
- **Product Lookup**: Get detailed specs (10-35+ fields) for any McMaster-Carr part number
- **Search**: Search for products and get part numbers from results
- **URL Generation**: Generate McMaster URLs without fetching (fast, no browser)
- **Cookie Persistence**: Browser profile saved for faster subsequent requests

## Installation

```bash
cd tools/mcmaster-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Or install dependencies directly:

```bash
pip install mcp seleniumbase beautifulsoup4
```

## Usage

### Run the server directly

```bash
python server.py
```

### Claude Code configuration

Add to `~/.claude.json` (or your MCP config):

```json
{
  "mcpServers": {
    "mcmaster-carr": {
      "command": "python",
      "args": ["/path/to/radiatron/tools/mcmaster-mcp/server.py"]
    }
  }
}
```

## Available Tools

### mcmaster_get_product

Get detailed product information by part number.

**Input:**
```json
{
  "part_number": "47865K23"
}
```

**Returns:**
- Product name
- 10-35+ specifications (material, size, pressure ratings, thread type, etc.)
- URL to product page

**Example output:**
```json
{
  "part_number": "47865K23",
  "name": "Brass Body On/Off Valve, with Lever Handle, 1/2 NPT Female, 32.3 Cv",
  "url": "https://www.mcmaster.com/47865K23",
  "specs": {
    "Pipe Size": "1/2",
    "Flow Coefficient (Cv)": "32.3",
    "Maximum Pressure": "600 psi @ 100° F",
    "Body Material": "Brass",
    "Valve Type": "Ball",
    "Thread Type": "NPT"
  }
}
```

### mcmaster_search

Search McMaster-Carr and get products matching the query.

The search automatically navigates through McMaster's category structure to find actual product listings with part numbers and names.

**Input:**
```json
{
  "query": "ball valve brass"
}
```

**Returns:** List of products with part numbers and names (up to 50).

```json
{
  "query": "ball valve brass",
  "count": 22,
  "results": [
    {"part_number": "47865K23", "name": "Threaded On/Off Valves", "url": "..."},
    {"part_number": "4373K53", "name": "Diverting Valves", "url": "..."},
    {"part_number": "8151N11", "name": "Socket-Connect On/Off Valves", "url": "..."}
  ]
}
```

### mcmaster_download_cad

Download authentic 3D CAD models (STEP, SolidWorks, IGES, SAT, etc.) or 2D drawings (DWG, DXF, PDF) for any McMaster-Carr part number directly to disk with SHA-256 checksum verification.

**Input:**
```json
{
  "part_number": "91290A115",
  "file_format": "3-D STEP",
  "output_dir": "C:/path/to/downloads"
}
```

**Parameters:**
- `part_number` (string, required): McMaster-Carr part number (e.g., `'91290A115'`, `'9414T11'`, `'1497K24'`).
- `file_format` (string, optional): Desired format. Defaults to `'3-D STEP'`. Supports `'3-D STEP'`, `'3-D SolidWorks'`, `'3-D IGES'`, `'3-D SAT'`, `'2-D DWG'`, `'2-D DXF'`, `'2-D PDF'`.
- `output_dir` (string, optional): Target directory path. Defaults to `./downloads`.

**Returns:**
```json
{
  "success": true,
  "part_number": "91290A115",
  "format": "3-D STEP",
  "file_name": "91290A115_Black-Oxide Alloy Steel Socket Head Screw.STEP",
  "file_path": "C:\\path\\to\\downloads\\91290A115_Black-Oxide Alloy Steel Socket Head Screw.STEP",
  "size_bytes": 1593856,
  "sha256": "80fb2b75a40bbd08593a1cfbb42c556b68ce57ee4506c9a341e427d1421f19c4",
  "url": "https://www.mcmaster.com/91290A115"
}
```

### mcmaster_url

Generate McMaster URLs without fetching. Fast, no browser needed.

**Input (product):**
```json
{
  "part_number": "47865K19"
}
```

**Input (search):**
```json
{
  "search_query": "stainless steel bolt"
}
```

## How It Works

1. **SeleniumBase UC Mode** - Undetected Chromium driver bypasses bot detection
2. **Visible Browser** - McMaster blocks headless browsers, so a Chrome window briefly appears
3. **Cookie Persistence** - Browser profile saved to `~/.mcmaster-browser` for faster subsequent requests
4. **BeautifulSoup** - Parses spec tables from rendered HTML

## Limitations

- **Visible browser window**: McMaster detects headless browsers, so a Chrome window briefly appears during requests
- **First request slower**: ~5-8 seconds for browser startup, subsequent requests ~3-5 seconds
- **CSS class changes**: May break if McMaster updates their class naming conventions

## Files

- `server.py` - MCP server entry point
- `browser.py` - SeleniumBase browser automation
- `agent.py` - Product search agent with requirement parsing (CLI tool)
- `mcmaster.py` - Legacy CDP-mode client (deprecated, kept for reference)

## Development

Run tests:
```bash
python test_agent.py
python test_search.py
python test_cad.py
```

Test the browser directly:
```bash
python -c "from browser import McMasterBrowser; b = McMasterBrowser(); b.start(); print(b.get_product('47865K23'))"
```
