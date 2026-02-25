"""Jina AI search for Walmart products."""

import os
import time

import httpx
from rich.console import Console

from models import WalmartProduct

console = Console()

JINA_API_KEY = os.getenv("JINA_API_KEY", "")
MAX_RETRIES = 3
REQUEST_DELAY = 1.0  # seconds between Jina requests


def jina_search(query: str) -> list[dict]:
    """Search the web via Jina AI, filtering for Walmart results.

    Args:
        query: The search query (item name).

    Returns:
        A list of dicts with url, title, and snippet for Walmart results.
    """
    search_query = f"walmart grocery {query}"

    headers = {
        "Accept": "application/json",
    }
    if JINA_API_KEY:
        headers["Authorization"] = f"Bearer {JINA_API_KEY}"

    for attempt in range(MAX_RETRIES):
        try:
            response = httpx.get(
                f"https://s.jina.ai/{search_query}",
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            break
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
            if attempt < MAX_RETRIES - 1:
                wait = 2 ** (attempt + 1)
                console.print(
                    f"[yellow]Jina search attempt {attempt + 1} failed, "
                    f"retrying in {wait}s...[/]"
                )
                time.sleep(wait)
            else:
                console.print(f"[yellow]Jina search failed for '{query}':[/] {e}")
                return []

    results = []
    raw_results = data.get("data", [])
    for item in raw_results:
        url = item.get("url", "")
        if "walmart.com" in url:
            results.append({
                "url": url,
                "title": item.get("title", ""),
                "snippet": item.get("description", item.get("content", "")),
            })

    return results


def _parse_price_from_snippet(snippet: str) -> float | None:
    """Try to extract a price from a Jina search snippet.

    Args:
        snippet: The search result snippet text.

    Returns:
        A float price or None if no price found.
    """
    import re

    # Match patterns like $3.99, $12.50, etc.
    price_match = re.search(r"\$(\d+\.?\d*)", snippet)
    if price_match:
        try:
            return float(price_match.group(1))
        except ValueError:
            pass
    return None


def _parse_product_from_result(result: dict) -> WalmartProduct:
    """Parse a Jina search result into a WalmartProduct.

    Args:
        result: A dict with url, title, and snippet.

    Returns:
        A WalmartProduct model.
    """
    title = result.get("title", "Unknown Product")
    snippet = result.get("snippet", "")

    # Clean up title — often has " - Walmart.com" suffix
    title = title.replace(" - Walmart.com", "").strip()

    price = _parse_price_from_snippet(snippet)

    # Try to infer availability from snippet
    availability = None
    snippet_lower = snippet.lower()
    if "out of stock" in snippet_lower:
        availability = "Out of Stock"
    elif "pickup" in snippet_lower or "delivery" in snippet_lower or "add to cart" in snippet_lower:
        availability = "In Stock"

    return WalmartProduct(
        name=title,
        price=price,
        url=result.get("url", ""),
        availability=availability,
    )


def search_walmart(query: str) -> list[WalmartProduct]:
    """Search Jina for Walmart products and parse results.

    Args:
        query: The search query (grocery item name).

    Returns:
        A list of WalmartProduct models parsed from search results.
    """
    search_results = jina_search(query)
    if not search_results:
        return []

    products: list[WalmartProduct] = []
    for result in search_results[:5]:
        product = _parse_product_from_result(result)
        products.append(product)

    return products
