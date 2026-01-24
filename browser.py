# ABOUTME: McMaster-Carr browser automation controller.
# ABOUTME: Uses SeleniumBase UC mode to extract product data with authentication.

import os
import subprocess
import time
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup

# Default location for browser profile (persists cookies)
DEFAULT_PROFILE_DIR = Path.home() / ".mcmaster-browser"


@dataclass
class PageState:
    """Current state of the browser page."""
    url: str
    title: str
    page_type: str  # 'home', 'search', 'category', 'product', 'unknown'
    products: list = field(default_factory=list)  # List of ProductSummary
    raw_html: str = ""


@dataclass
class ProductSummary:
    """Brief product info from search results."""
    part_number: str
    name: str = ""
    url: str = ""


@dataclass
class ProductDetails:
    """Full product details."""
    part_number: str
    name: str
    url: str
    specs: dict = field(default_factory=dict)


class McMasterBrowser:
    """Browser automation for McMaster-Carr.

    Uses SeleniumBase UC (undetected chromium) mode to access product data.
    Requires authentication for full product details.
    """

    # 1Password paths for credentials
    OP_USERNAME_PATH = "op://Private/7yhzss3x346tqnyy3l43k3uiym/username"
    OP_PASSWORD_PATH = "op://Private/7yhzss3x346tqnyy3l43k3uiym/password"

    def __init__(self, headless: bool = False, username: str = None, password: str = None,
                 profile_dir: str = None):
        # Note: headless=False by default because McMaster detects headless browsers
        self.headless = headless
        self._sb = None
        self._logged_in = False
        self._username = username
        self._password = password
        self._profile_dir = Path(profile_dir) if profile_dir else DEFAULT_PROFILE_DIR
        self._profile_dir.mkdir(parents=True, exist_ok=True)

    def start(self):
        """Start the browser session."""
        if self._sb is None:
            from seleniumbase import SB
            # Use headless2 mode (newer, harder to detect) for headless operation
            # Use user_data_dir to persist cookies across sessions
            if self.headless:
                self._sb_context = SB(
                    uc=True, headless2=True, test=True,
                    user_data_dir=str(self._profile_dir)
                )
            else:
                self._sb_context = SB(
                    uc=True, headless=False, test=True,
                    user_data_dir=str(self._profile_dir)
                )
            self._sb = self._sb_context.__enter__()
        return self

    def _get_credentials(self) -> tuple[str, str]:
        """Get McMaster credentials from env vars, params, or 1Password."""
        username = self._username or os.environ.get("MCMASTER_USERNAME")
        password = self._password or os.environ.get("MCMASTER_PASSWORD")

        if not username or not password:
            # Try 1Password
            try:
                if not username:
                    result = subprocess.run(
                        ["op", "read", self.OP_USERNAME_PATH],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0:
                        username = result.stdout.strip()

                if not password:
                    result = subprocess.run(
                        ["op", "read", self.OP_PASSWORD_PATH],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0:
                        password = result.stdout.strip()
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        if not username or not password:
            raise RuntimeError(
                "McMaster credentials not found. Set MCMASTER_USERNAME and "
                "MCMASTER_PASSWORD environment variables, pass to constructor, "
                "or configure 1Password CLI."
            )

        return username, password

    def login(self) -> bool:
        """Log into McMaster-Carr. Returns True on success."""
        if self._logged_in:
            return True

        if not self._sb:
            self.start()

        username, password = self._get_credentials()

        # Go to McMaster home
        self._sb.open("https://www.mcmaster.com/")
        time.sleep(2)

        # Click login dropdown
        self._sb.click("text=Log in")
        time.sleep(2)

        # Fill credentials
        self._sb.type("#Email", username)
        self._sb.type("#Password", password)
        time.sleep(0.5)

        # Click login button
        self._sb.click('button[class*="_button_1pdkk"]')
        time.sleep(3)

        # Verify login succeeded by checking page state
        html = self._sb.get_page_source()
        if "Log Out" in html or "Sign Out" in html:
            self._logged_in = True
            return True

        # Check if we can access product details
        self._sb.open("https://www.mcmaster.com/47865K23")
        time.sleep(2)
        html = self._sb.get_page_source()
        if "Log in to view" not in html and "Pipe Size" in html:
            self._logged_in = True
            return True

        return False

    def ensure_logged_in(self):
        """Ensure session is ready. Login only needed for headless mode.

        With visible browser (headless=False), no login is required.
        McMaster only blocks headless browsers, not regular browser access.
        """
        if self._logged_in:
            return

        # Visible browser doesn't need login
        if not self.headless:
            self._logged_in = True
            return

        # Headless mode may need login - test access
        self._sb.open("https://www.mcmaster.com/47865K23")
        time.sleep(2)
        html = self._sb.get_page_source()
        if "Log in to view" not in html and "Pipe Size" in html:
            self._logged_in = True
            return

        # Need to login for headless
        if not self.login():
            raise RuntimeError("Failed to log into McMaster-Carr")

    def stop(self):
        """Stop the browser session."""
        if self._sb is not None:
            try:
                self._sb_context.__exit__(None, None, None)
            except Exception:
                pass
            self._sb = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.stop()

    def goto(self, url: str) -> PageState:
        """Navigate to a URL and return page state."""
        if not self._sb:
            self.start()

        self._sb.open(url)
        time.sleep(3)

        return self._analyze_page()

    def search(self, query: str, click_into_category: bool = True, max_depth: int = 2) -> PageState:
        """Perform a search and return results.

        McMaster's category pages don't show product tables directly - you need
        to click into subcategories to see actual products. If click_into_category
        is True, we'll automatically drill down to find real product listings.

        Args:
            query: Search query
            click_into_category: Auto-navigate into subcategories to find products
            max_depth: Maximum number of category levels to drill into (default 2)
        """
        encoded_query = query.replace(' ', '+')
        url = f"https://www.mcmaster.com/{encoded_query}"
        state = self.goto(url)

        # Category pages show tiles but not actual products with part numbers
        # Keep drilling down until we find real product listings
        depth = 0
        while click_into_category and len(state.products) < 20 and depth < max_depth:
            clicked_state = self._click_into_product_category()
            # Stop if we didn't get more products
            if len(clicked_state.products) <= len(state.products):
                break
            state = clicked_state
            depth += 1

        return state

    def _click_into_product_category(self) -> PageState:
        """Click into a product category tile to load the product table.

        McMaster uses category tiles that need to be clicked to reveal products.
        These tiles typically have outerContainer or GridCell classes.
        """
        if not self._sb:
            return self._analyze_page()

        try:
            # Try different selectors for category tiles
            selectors = [
                '[class*="outerContainer"]',  # Category tiles
                '[class*="GridCell"] a',       # Grid cell links
                '[class*="flexTable"] a',      # Flex table links
            ]

            for selector in selectors:
                tiles = self._sb.find_elements(selector)
                if tiles:
                    # Click the first tile that looks like a category link
                    for tile in tiles[:3]:
                        try:
                            href = tile.get_attribute('href') or ''
                            # Skip if it's already a product page (has part number pattern)
                            if re.search(r'/\d{4,5}[A-Z]{1,2}\d{1,3}(?:\?|$)', href, re.IGNORECASE):
                                continue
                            tile.click()
                            time.sleep(3)
                            return self._analyze_page()
                        except Exception:
                            continue
        except Exception:
            pass

        return self._analyze_page()

    def _is_blocked(self, html: str) -> bool:
        """Check if page is showing login/block message."""
        return "Log in to view" in html

    def _handle_login_prompt(self, html: str) -> str:
        """Handle login prompt if it appears on a page. Returns updated HTML."""
        if not self._is_blocked(html):
            return html

        # Try filling login form if present
        try:
            username, password = self._get_credentials()
            self._sb.type("#Email", username)
            self._sb.type("#Password", password)
            time.sleep(0.5)
            self._sb.click('button[class*="_button_1pdkk"]')
            time.sleep(5)
            return self._sb.get_page_source()
        except Exception:
            # Form not present or failed
            return html

    def get_product(self, part_number: str) -> ProductDetails:
        """Get full product details by part number."""
        url = f"https://www.mcmaster.com/{part_number}"

        if not self._sb:
            self.start()

        # Ensure we're logged in to see full product details
        self.ensure_logged_in()

        self._sb.open(url)
        time.sleep(3)

        html = self._sb.get_page_source()

        # Handle additional login prompt if it appears
        html = self._handle_login_prompt(html)

        soup = BeautifulSoup(html, 'html.parser')

        # Get product name from title
        title_elem = soup.find('title')
        name = ""
        if title_elem:
            name = title_elem.get_text(strip=True).replace(" | McMaster-Carr", "")

        # Extract specs from spec table
        specs = self._extract_specs(soup)

        return ProductDetails(
            part_number=part_number,
            name=name,
            url=url,
            specs=specs
        )

    def _analyze_page(self) -> PageState:
        """Analyze the current page and extract structured data."""
        if not self._sb:
            raise RuntimeError("Browser not initialized")

        html = self._sb.get_page_source()
        url = self._sb.get_current_url()
        soup = BeautifulSoup(html, 'html.parser')

        # Get title
        title_elem = soup.find('title')
        title = title_elem.get_text(strip=True) if title_elem else ""

        # Determine page type
        page_type = self._detect_page_type(url, title, soup)

        # Extract products if on a listing page
        products = []
        if page_type in ('search', 'category'):
            products = self._extract_product_list(soup)

        return PageState(
            url=url,
            title=title,
            page_type=page_type,
            products=products,
            raw_html=html
        )

    def _detect_page_type(self, url: str, title: str, soup: BeautifulSoup) -> str:
        """Detect what type of page we're on."""
        if url == "https://www.mcmaster.com/" or title == "McMaster-Carr":
            return 'home'

        # Check for product page (has spec table)
        if self._has_spec_table(soup):
            return 'product'

        # Check for search/category
        if ' | McMaster-Carr' in title:
            return 'search'

        return 'unknown'

    def _has_spec_table(self, soup: BeautifulSoup) -> bool:
        """Check if page has a product spec table."""
        for elem in soup.find_all(class_=True):
            classes = ' '.join(elem.get('class', []))
            if 'product-detail-spec-table' in classes:
                return True
        return False

    def _extract_specs(self, soup: BeautifulSoup) -> dict:
        """Extract product specs from the spec table."""
        specs = {}

        # Find spec table rows - they use CSS module classes with hash suffixes
        # Pattern: _product-detail-spec-table-row_XXXXX_N
        # Each row has two tableCell children: first is label, second is value
        for row in soup.find_all(class_=True):
            classes = ' '.join(row.get('class', []))
            if 'spec-table-row' in classes and 'indented' not in classes:
                # Get direct children with tableCell class
                cells = []
                for child in row.find_all(class_=True, recursive=False):
                    child_classes = ' '.join(child.get('class', []))
                    if 'tableCell' in child_classes:
                        cells.append(child.get_text(strip=True))

                if len(cells) >= 2:
                    label = cells[0]
                    value = cells[1]
                    if label and value:
                        specs[label] = value

        return specs

    def _extract_product_list(self, soup: BeautifulSoup) -> list[ProductSummary]:
        """Extract list of products from a search/category page.

        McMaster renders products in table cells. Part numbers appear in:
        1. Link hrefs (e.g., href="/47865K23")
        2. Image srcset URLs (e.g., 47865k23p3-c03a-digital.png)

        We collect from all sources and deduplicate.
        """
        products = []
        # McMaster part numbers: 4-5 digits, 1-2 uppercase letters, 1-3 digits
        # Must start with non-zero digit (to filter out GUIDs)
        part_number_pattern = re.compile(r'\b([1-9]\d{3,4}[A-Z]{1,2}\d{1,3})\b', re.IGNORECASE)

        # Look for product links with part number patterns in href
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            match = re.search(r'[/=]([1-9]\d{3,4}[A-Z]{1,2}\d{1,3})(?:\?|$|/|&)', href, re.IGNORECASE)
            if match:
                part_num = match.group(1).upper()
                name = link.get_text(strip=True) or ""
                # Skip navigation/category links (they have "/" in the text or very short)
                if len(name) > 5 and len(name) < 200 and "/" not in name:
                    products.append(ProductSummary(
                        part_number=part_num,
                        name=name[:100],
                        url=f"https://www.mcmaster.com/{part_num}"
                    ))

        # Also look in image srcset URLs (McMaster embeds part numbers in filenames)
        for img in soup.find_all('img'):
            srcset = img.get('srcset', '') or img.get('src', '')
            matches = part_number_pattern.findall(srcset)
            for part_num_raw in matches:
                part_num = part_num_raw.upper()
                # Get name from alt attribute
                name = img.get('alt', '') or img.get('title', '') or ""
                if name and len(name) < 200:
                    products.append(ProductSummary(
                        part_number=part_num,
                        name=name[:100],
                        url=f"https://www.mcmaster.com/{part_num}"
                    ))

        # Deduplicate by part number, preferring entries with names
        seen = {}
        for p in products:
            if p.part_number not in seen:
                seen[p.part_number] = p
            elif p.name and not seen[p.part_number].name:
                # Replace nameless entry with one that has a name
                seen[p.part_number] = p

        unique = list(seen.values())
        return unique[:50]  # Return up to 50 products

    @staticmethod
    def get_product_url(part_number: str) -> str:
        """Generate product URL."""
        return f"https://www.mcmaster.com/{part_number}"

    @staticmethod
    def get_search_url(query: str) -> str:
        """Generate search URL."""
        return f"https://www.mcmaster.com/{query.replace(' ', '+')}"
