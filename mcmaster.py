# ABOUTME: McMaster-Carr web scraping client using SeleniumBase CDP mode.
# ABOUTME: Uses CDP mode to bypass anti-bot protection and extract product data.

import re
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProductInfo:
    """Product information from McMaster-Carr."""
    part_number: str
    name: str
    description: Optional[str] = None
    price: Optional[str] = None
    specs: dict = field(default_factory=dict)
    url: str = ""
    image_url: Optional[str] = None
    in_stock: Optional[bool] = None
    category: Optional[str] = None


@dataclass
class SearchResult:
    """Search result from McMaster-Carr."""
    part_number: str
    name: str
    description: Optional[str] = None
    url: str = ""


class McMasterClient:
    """Client for scraping McMaster-Carr website using SeleniumBase CDP mode."""

    BASE_URL = "https://www.mcmaster.com"

    def __init__(self, headless: bool = True):
        self.headless = headless

    def close(self):
        """Close the browser (no-op, we use context managers)."""
        pass

    def get_product(self, part_number: str) -> ProductInfo:
        """Get product information by part number."""
        url = f"{self.BASE_URL}/{part_number}"

        try:
            from seleniumbase import SB

            with SB(uc=True, headless=self.headless, test=True) as sb:
                sb.activate_cdp_mode(url)

                # Wait for page to load
                time.sleep(3)

                # Extract product info from page
                html = sb.cdp.get_page_source()
                info = self._parse_product_html(html, part_number)
                info.url = url

                return info

        except Exception as e:
            return ProductInfo(
                part_number=part_number,
                name=f"McMaster-Carr {part_number}",
                url=url,
                description=f"Error loading product: {str(e)}"
            )

    def _parse_product_html(self, html: str, part_number: str) -> ProductInfo:
        """Parse product information from HTML."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        # Extract product name from title (most reliable)
        name = None
        title = soup.find('title')
        if title:
            title_text = title.get_text(strip=True)
            if title_text and title_text != "McMaster-Carr":
                # Format: "Product Name | McMaster-Carr"
                name = title_text.replace(" | McMaster-Carr", "").replace("McMaster-Carr", "").strip()

        # Fallback: try CSS module classes with partial matching
        if not name:
            for elem in soup.find_all(class_=True):
                classes = ' '.join(elem.get('class', []))
                if 'productDetailHeader' in classes.lower():
                    text = elem.get_text(strip=True)
                    if text and len(text) < 500:
                        name = text
                        break

        name = name or f"Product {part_number}"

        # Extract description from product-detail-copy elements
        description = None
        for elem in soup.find_all(class_=True):
            classes = ' '.join(elem.get('class', []))
            if 'product-detail-copy' in classes and 'padding' not in classes:
                text = elem.get_text(strip=True)
                if text and len(text) > 10:
                    description = text
                    break

        # Extract price - look for dollar amounts
        price = None
        price_pattern = re.compile(r'\$[\d,]+\.?\d*')
        for elem in soup.find_all(class_=True):
            classes = ' '.join(elem.get('class', []))
            if 'price' in classes.lower():
                text = elem.get_text(strip=True)
                match = price_pattern.search(text)
                if match:
                    price = match.group()
                    break

        # If no price class found, search more broadly
        if not price:
            all_text = soup.get_text()
            matches = price_pattern.findall(all_text)
            if matches:
                # Usually the first price is the unit price
                price = matches[0]

        # Extract specs from spec table
        specs = {}
        for elem in soup.find_all(class_=True):
            classes = ' '.join(elem.get('class', []))
            if 'spec-table-body' in classes:
                # Found the spec table body - extract rows
                rows = elem.find_all(class_=lambda c: c and 'spec-table-row' in ' '.join(c if isinstance(c, list) else [c]))
                for row in rows:
                    cells = row.find_all(class_=lambda c: c and 'tableCell' in ' '.join(c if isinstance(c, list) else [c]))
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        if label and value and len(label) < 100:
                            specs[label] = value
                break

        # Extract image URL
        image_url = None
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if 'mcmaster' in src and 'product' in src.lower():
                image_url = src
                break

        # Check stock status
        in_stock = None
        page_text = html.lower()
        if "in stock" in page_text:
            in_stock = True
        elif "out of stock" in page_text or "backorder" in page_text:
            in_stock = False

        # Extract category from breadcrumbs
        category = None
        for elem in soup.find_all(class_=True):
            classes = ' '.join(elem.get('class', []))
            if 'breadcrumb' in classes.lower():
                category = elem.get_text(strip=True)
                break

        return ProductInfo(
            part_number=part_number,
            name=name,
            description=description,
            price=price,
            specs=specs,
            image_url=image_url,
            in_stock=in_stock,
            category=category
        )

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Search for products.

        Note: McMaster uses complex iframes for search results which are
        difficult to scrape reliably. This returns a search URL that can
        be opened in a browser.
        """
        # McMaster loads search in iframes which are hard to scrape
        # Return a helpful result pointing to the search URL
        url = self.get_search_url(query)
        return [SearchResult(
            part_number="",
            name=f"Search McMaster-Carr for: {query}",
            description="Open this URL in a browser to see results",
            url=url
        )]

    @staticmethod
    def get_product_url(part_number: str) -> str:
        """Generate product URL without fetching."""
        return f"https://www.mcmaster.com/{part_number}"

    @staticmethod
    def get_search_url(query: str) -> str:
        """Generate search URL without fetching."""
        return f"https://www.mcmaster.com/{query.replace(' ', '+')}"
