# ABOUTME: McMaster-Carr product search agent.
# ABOUTME: Uses browser automation to find products matching requirements.

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from browser import McMasterBrowser, PageState, ProductSummary, ProductDetails


@dataclass
class ProductRequirement:
    """Structured product requirements."""
    keywords: list[str] = field(default_factory=list)
    size: Optional[str] = None  # e.g., "1-1/4 inch", "3/4 NPT"
    material: Optional[str] = None  # e.g., "brass", "stainless steel"
    thread_type: Optional[str] = None  # e.g., "NPT", "BSP"
    voltage: Optional[str] = None  # e.g., "24V", "120V"
    features: list[str] = field(default_factory=list)  # e.g., ["motorized", "position feedback"]
    max_price: Optional[float] = None
    raw_query: str = ""


@dataclass
class ProductCandidate:
    """A product being evaluated."""
    part_number: str
    name: str
    url: str
    specs: dict = field(default_factory=dict)
    match_score: float = 0.0
    match_reasons: list[str] = field(default_factory=list)
    mismatch_reasons: list[str] = field(default_factory=list)


class McMasterAgent:
    """Agent for finding products on McMaster-Carr."""

    def __init__(self, headless: bool = True, verbose: bool = True):
        self.headless = headless
        self.verbose = verbose
        self.browser: Optional[McMasterBrowser] = None
        self.candidates: list[ProductCandidate] = []

    def log(self, message: str):
        """Log agent activity."""
        if self.verbose:
            print(f"[Agent] {message}")

    def parse_requirements(self, query: str) -> ProductRequirement:
        """Parse natural language query into structured requirements."""
        req = ProductRequirement(raw_query=query)
        query_lower = query.lower()

        # Extract size patterns
        size_patterns = [
            r'(\d+[-/]?\d*)\s*(?:inch|in|")',
            r'(\d+[-/]?\d*)\s*(?:npt|bsp)',
            r'(\d+)\s*mm',
        ]
        for pattern in size_patterns:
            match = re.search(pattern, query_lower)
            if match:
                req.size = match.group(0)
                break

        # Extract material
        materials = ['brass', 'stainless steel', 'stainless', 'bronze', 'steel', 'cast iron', 'pvc', 'cpvc']
        for mat in materials:
            if mat in query_lower:
                req.material = mat
                break

        # Extract thread type
        thread_types = ['npt', 'bsp', 'bspt', 'unf', 'unc']
        for tt in thread_types:
            if tt in query_lower:
                req.thread_type = tt.upper()
                break

        # Extract voltage
        voltage_match = re.search(r'(\d+)\s*v(?:olt|dc|ac)?', query_lower)
        if voltage_match:
            req.voltage = voltage_match.group(1) + "V"

        # Extract features
        feature_keywords = ['motorized', 'electric', 'actuator', 'position feedback',
                          'limit switch', 'manual override', 'fail-safe']
        for feat in feature_keywords:
            if feat in query_lower:
                req.features.append(feat)

        # Extract search keywords (nouns)
        # Remove the structured parts and keep main keywords
        keywords = []
        main_terms = ['valve', 'ball valve', 'gate valve', 'butterfly valve',
                     'actuator', 'motor', 'radiator', 'fitting', 'adapter']
        for term in main_terms:
            if term in query_lower:
                keywords.append(term)

        req.keywords = keywords if keywords else query.split()[:3]

        return req

    def build_search_query(self, req: ProductRequirement) -> str:
        """Build McMaster search query from requirements."""
        parts = []

        # Add main keywords
        parts.extend(req.keywords)

        # Add size if specified
        if req.size:
            parts.append(req.size)

        # Add material if specified
        if req.material:
            parts.append(req.material)

        # Add key features
        if 'motorized' in req.features or 'electric' in req.features:
            if 'motorized' not in parts and 'electric' not in parts:
                parts.append('motorized')

        return ' '.join(parts)

    def evaluate_product(self, product: ProductDetails, req: ProductRequirement) -> ProductCandidate:
        """Evaluate how well a product matches requirements."""
        candidate = ProductCandidate(
            part_number=product.part_number,
            name=product.name,
            url=product.url,
            specs=product.specs
        )

        score = 0.0
        specs_text = json.dumps(candidate.specs).lower()
        name_lower = candidate.name.lower()

        # Check size match
        if req.size:
            size_normalized = req.size.replace('"', '').replace(' ', '')
            if req.size in specs_text or size_normalized in specs_text.replace(' ', ''):
                score += 30
                candidate.match_reasons.append(f"Size matches: {req.size}")
            else:
                candidate.mismatch_reasons.append(f"Size not found: {req.size}")

        # Check material match
        if req.material:
            if req.material.lower() in specs_text or req.material.lower() in name_lower:
                score += 20
                candidate.match_reasons.append(f"Material matches: {req.material}")
            else:
                candidate.mismatch_reasons.append(f"Material not found: {req.material}")

        # Check thread type
        if req.thread_type:
            if req.thread_type.lower() in specs_text:
                score += 15
                candidate.match_reasons.append(f"Thread type matches: {req.thread_type}")

        # Check voltage
        if req.voltage:
            if req.voltage.lower() in specs_text:
                score += 15
                candidate.match_reasons.append(f"Voltage matches: {req.voltage}")

        # Check features
        for feature in req.features:
            if feature.lower() in specs_text or feature.lower() in name_lower:
                score += 10
                candidate.match_reasons.append(f"Has feature: {feature}")

        # Bonus for being the right general category
        for kw in req.keywords:
            if kw.lower() in name_lower:
                score += 5

        candidate.match_score = score
        return candidate

    def search(self, query: str, max_candidates: int = 5) -> list[ProductCandidate]:
        """Search for products matching the query."""
        self.log(f"Parsing requirements: {query}")
        req = self.parse_requirements(query)
        self.log(f"Parsed: keywords={req.keywords}, size={req.size}, material={req.material}, features={req.features}")

        search_query = self.build_search_query(req)
        self.log(f"Search query: {search_query}")

        self.candidates = []

        with McMasterBrowser(headless=self.headless) as browser:
            self.browser = browser

            # Perform search
            self.log(f"Navigating to McMaster search...")
            state = browser.search(search_query)
            self.log(f"Page type: {state.page_type}, Title: {state.title}")

            if state.page_type == 'product':
                # Direct hit on a product page - extract part number from URL
                self.log("Direct product hit, extracting details...")
                # Extract part number from URL (e.g., https://www.mcmaster.com/47865K23)
                import re
                part_match = re.search(r'/(\d{4,}[A-Z]{1,2}\d{1,3})(?:\?|$|/)', state.url)
                if part_match:
                    part_number = part_match.group(1)
                    details = browser.get_product(part_number)
                    candidate = self.evaluate_product(details, req)
                    self.candidates.append(candidate)

            elif state.page_type in ('search', 'category', 'unknown'):
                # Got search results, need to explore products
                products = state.products
                self.log(f"Found {len(products)} products in listing")

                if not products:
                    # Try alternative: navigate directly to likely category
                    self.log("No products found in listing, trying category navigation...")
                    # For valves, try the valve category
                    if 'valve' in search_query.lower():
                        state = browser.goto('https://www.mcmaster.com/valves')
                        self.log(f"Valve category page: {state.page_type}")

                # Explore top products
                explored = 0
                for i, product_summary in enumerate(products[:max_candidates * 2]):
                    if explored >= max_candidates:
                        break

                    self.log(f"Exploring product {i+1}: {product_summary.part_number} - {product_summary.name[:50]}")

                    try:
                        # Get full product details
                        details = browser.get_product(product_summary.part_number)
                        candidate = self.evaluate_product(details, req)
                        self.candidates.append(candidate)
                        explored += 1
                        self.log(f"  Score: {candidate.match_score}, Matches: {candidate.match_reasons}")

                    except Exception as e:
                        self.log(f"  Error exploring product: {e}")

            self.browser = None

        # Sort by score
        self.candidates.sort(key=lambda c: c.match_score, reverse=True)

        return self.candidates

    def format_results(self, candidates: list[ProductCandidate] = None) -> str:
        """Format results for display."""
        if candidates is None:
            candidates = self.candidates

        if not candidates:
            return "No matching products found."

        lines = ["# McMaster-Carr Product Recommendations\n"]

        for i, c in enumerate(candidates, 1):
            lines.append(f"## {i}. {c.name}")
            lines.append(f"**Part Number:** {c.part_number}")
            lines.append(f"**URL:** {c.url}")
            lines.append(f"**Match Score:** {c.match_score}")
            lines.append("")

            if c.match_reasons:
                lines.append("**Matches:**")
                for reason in c.match_reasons:
                    lines.append(f"- {reason}")
                lines.append("")

            if c.mismatch_reasons:
                lines.append("**Potential Issues:**")
                for reason in c.mismatch_reasons:
                    lines.append(f"- {reason}")
                lines.append("")

            if c.specs:
                lines.append("**Key Specs:**")
                for k, v in list(c.specs.items())[:10]:
                    lines.append(f"- {k}: {v}")
                lines.append("")

            lines.append("---\n")

        return "\n".join(lines)


def main():
    """Test the agent."""
    import sys

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "motorized ball valve 1-1/4 inch brass 24V"

    print(f"Searching for: {query}\n")

    agent = McMasterAgent(headless=True, verbose=True)
    candidates = agent.search(query, max_candidates=3)

    print("\n" + "=" * 60 + "\n")
    print(agent.format_results(candidates))


if __name__ == "__main__":
    main()
