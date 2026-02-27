"""Agent tools — Walmart search, Apple Notes, and notifications."""

import json
import os
import re
import subprocess
import time
from datetime import datetime
from urllib.parse import quote_plus

import httpx
from rich.console import Console

from schemas import WalmartProduct

console = Console()

# --- Jina / Walmart Search ---

JINA_API_KEY = os.getenv("JINA_API_KEY", "")
MAX_RETRIES = 3
REQUEST_DELAY = 1.0  # seconds between Jina requests
SCRAPLING_REQUEST_DELAY = 2.5  # seconds between Scrapling requests


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


def jina_read(url: str) -> str:
    """Read a URL via Jina Reader API and return the page content as text.

    Args:
        url: The URL to read.

    Returns:
        The page content as markdown text, or empty string on failure.
    """
    headers = {
        "Accept": "application/json",
        "X-Return-Format": "markdown",
    }
    if JINA_API_KEY:
        headers["Authorization"] = f"Bearer {JINA_API_KEY}"

    try:
        response = httpx.get(
            f"https://r.jina.ai/{url}",
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("data", {}).get("content", "")
    except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException):
        return ""


def _parse_price_from_text(text: str) -> float | None:
    """Extract a price from text content."""
    current_match = re.search(
        r"(?:current price|now)\s*\$(\d+\.?\d*)", text, re.IGNORECASE
    )
    if current_match:
        try:
            return float(current_match.group(1))
        except ValueError:
            pass

    price_match = re.search(r"\$(\d+\.\d{2})", text)
    if price_match:
        try:
            return float(price_match.group(1))
        except ValueError:
            pass
    return None


def _parse_product_from_result(result: dict) -> WalmartProduct:
    """Parse a Jina search result into a WalmartProduct."""
    title = result.get("title", "Unknown Product")
    snippet = result.get("snippet", "")

    title = title.replace(" - Walmart.com", "").strip()
    price = _parse_price_from_text(snippet)

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


def _enrich_product(product: WalmartProduct) -> WalmartProduct:
    """Read the product's Walmart page via Jina Reader to fill in missing data."""
    if product.price and product.availability:
        return product

    if "/ip/" not in product.url:
        return product

    page_content = jina_read(product.url)
    if not page_content:
        return product

    if not product.price:
        product.price = _parse_price_from_text(page_content)

    if not product.availability:
        lower = page_content.lower()
        if "out of stock" in lower:
            product.availability = "Out of Stock"
        elif any(w in lower for w in ["add to cart", "pickup", "delivery"]):
            product.availability = "In Stock"

    if not product.brand:
        brand_match = re.search(r"(?:brand|by)\s*[:\-]?\s*([A-Z][\w\s&]+)", page_content)
        if brand_match:
            product.brand = brand_match.group(1).strip()[:30]

    if not product.size:
        size_match = re.search(
            r"(\d+\.?\d*\s*(?:oz|lb|lbs|ct|count|pack|kg|g|fl oz|gal|gallon))",
            page_content, re.IGNORECASE
        )
        if size_match:
            product.size = size_match.group(1).strip()

    return product


def _search_walmart_jina(query: str) -> list[WalmartProduct]:
    """Search Jina for Walmart products, enrich top result with page data."""
    search_results = jina_search(query)
    if not search_results:
        return []

    # Filter to actual product pages (must have /ip/ in URL)
    search_results = [r for r in search_results if "/ip/" in r.get("url", "")]
    if not search_results:
        return []

    products: list[WalmartProduct] = []
    for i, result in enumerate(search_results[:5]):
        product = _parse_product_from_result(result)
        if i < 2 and not product.price:
            product = _enrich_product(product)
        products.append(product)

    time.sleep(REQUEST_DELAY)
    return products


# --- Scrapling / Stealth Browser ---


def _extract_next_data(page) -> dict | None:
    """Extract __NEXT_DATA__ JSON from a Walmart page."""
    scripts = page.css('script#__NEXT_DATA__')
    if not scripts:
        return None
    try:
        return json.loads(scripts[0].text)
    except (json.JSONDecodeError, AttributeError, IndexError):
        return None


def _raw_item_to_product(item: dict) -> WalmartProduct | None:
    """Convert a raw Walmart search result item to a WalmartProduct."""
    name = item.get("name") or item.get("title", "")
    if not name:
        return None

    # Price extraction — Walmart uses several structures depending on page version
    price = None

    # 1. Top-level "price" field (current Walmart format, float or int)
    top_price = item.get("price")
    if isinstance(top_price, (int, float)) and top_price > 0:
        price = float(top_price)

    # 2. priceInfo fields (linePrice is a string like "$3.47", or nested dicts)
    if price is None:
        price_info = item.get("priceInfo") or item.get("price_info") or {}
        if isinstance(price_info, dict):
            # Try linePrice first (current format: string "$3.47")
            line_price = price_info.get("linePrice") or price_info.get("linePriceDisplay")
            if isinstance(line_price, str) and "$" in line_price:
                match = re.search(r"(\d+\.?\d*)", line_price)
                if match:
                    price = float(match.group(1))
            # Try currentPrice (older format: dict with "price" key)
            if price is None:
                current = price_info.get("currentPrice") or price_info.get("current_price") or {}
                if isinstance(current, dict):
                    p = current.get("price") or current.get("priceString")
                    if isinstance(p, (int, float)):
                        price = float(p)
                    elif isinstance(p, str):
                        match = re.search(r"(\d+\.?\d*)", p)
                        if match:
                            price = float(match.group(1))
            # Try direct price field in priceInfo
            if price is None:
                p = price_info.get("price")
                if isinstance(p, (int, float)) and p > 0:
                    price = float(p)

    if isinstance(price, str):
        match = re.search(r"(\d+\.?\d*)", price)
        price = float(match.group(1)) if match else None

    canonical = item.get("canonicalUrl") or item.get("canonical_url") or ""
    product_url = item.get("url", "")
    if canonical and not canonical.startswith("http"):
        product_url = f"https://www.walmart.com{canonical}"
    elif canonical:
        product_url = canonical
    elif not product_url:
        us_item_id = item.get("usItemId") or item.get("id", "")
        if us_item_id:
            product_url = f"https://www.walmart.com/ip/{us_item_id}"

    image_url = None
    image_info = item.get("imageInfo") or item.get("image_info") or {}
    if isinstance(image_info, dict):
        image_url = image_info.get("thumbnailUrl") or image_info.get("url")
    if not image_url:
        image_url = item.get("image") or item.get("thumbnailUrl")

    availability = None
    avail_status = item.get("availabilityStatusV2") or item.get("availabilityStatus") or {}
    if isinstance(avail_status, dict):
        display = avail_status.get("display") or avail_status.get("value", "")
        if display:
            availability = display
    elif isinstance(avail_status, str):
        availability = avail_status
    if not availability:
        flag = item.get("flag", "")
        if isinstance(flag, str) and flag:
            availability = flag

    brand = item.get("brand") or None
    if isinstance(brand, list) and brand:
        brand = brand[0]
    elif isinstance(brand, dict):
        brand = brand.get("name")

    size = None
    variants = item.get("variantCriteria") or []
    for variant in variants if isinstance(variants, list) else []:
        if isinstance(variant, dict) and variant.get("name", "").lower() in ("size", "count"):
            entries = variant.get("variantList") or []
            if entries and isinstance(entries, list):
                selected = next(
                    (e for e in entries if isinstance(e, dict) and e.get("selected")),
                    entries[0] if entries else None,
                )
                if selected and isinstance(selected, dict):
                    size = selected.get("name")
                    break

    return WalmartProduct(
        name=name,
        price=price,
        url=product_url,
        image_url=image_url,
        availability=availability,
        size=size,
        brand=brand,
    )


def _parse_search_results(next_data: dict) -> list[WalmartProduct]:
    """Parse __NEXT_DATA__ JSON from a Walmart search page into products."""
    products: list[WalmartProduct] = []

    try:
        props = next_data.get("props", {})
        page_props = props.get("pageProps", {})
        initial_data = page_props.get("initialData", {})
        search_result = initial_data.get("searchResult", {})
        item_stacks = search_result.get("itemStacks", [])

        for stack in item_stacks:
            if not isinstance(stack, dict):
                continue
            items = stack.get("items", [])
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("__typename", "") or item.get("type", "")
                if item_type in ("AdTile", "HorizontalChipModuleConfigs", "TileTakeOverProductPlacement"):
                    continue
                product = _raw_item_to_product(item)
                if product:
                    products.append(product)
    except (AttributeError, TypeError):
        pass

    return products


def _parse_product_page(next_data: dict) -> dict:
    """Parse __NEXT_DATA__ JSON from a Walmart product page."""
    enrichments: dict = {}

    try:
        props = next_data.get("props", {})
        page_props = props.get("pageProps", {})
        initial_data = page_props.get("initialData", {})
        product_data = initial_data.get("data", {}).get("product", {})

        price_info = product_data.get("priceInfo", {})
        current = price_info.get("currentPrice", {})
        if isinstance(current, dict):
            price = current.get("price")
            if price is not None:
                enrichments["price"] = float(price)

        brand = product_data.get("brand")
        if brand:
            enrichments["brand"] = brand

        avail = product_data.get("availabilityStatus")
        if avail:
            enrichments["availability"] = avail

        image_info = product_data.get("imageInfo", {})
        if isinstance(image_info, dict):
            img = image_info.get("thumbnailUrl") or image_info.get("url")
            if img:
                enrichments["image_url"] = img

    except (AttributeError, TypeError):
        pass

    return enrichments


def _scrape_walmart_search(query: str) -> list[WalmartProduct]:
    """Scrape Walmart search results using Scrapling stealth browser."""
    from scrapling.fetchers import StealthyFetcher

    url = f"https://www.walmart.com/search?q={quote_plus(query)}"
    console.print(f"[dim]Scraping Walmart search: {query}[/]")

    page = StealthyFetcher.fetch(url, headless=True, block_images=True)

    next_data = _extract_next_data(page)
    if not next_data:
        console.print("[yellow]No __NEXT_DATA__ found on search page[/]")
        return []

    products = _parse_search_results(next_data)

    if products:
        console.print(f"[dim]Scrapling found {len(products)} products[/]")
    else:
        console.print("[yellow]No products parsed from __NEXT_DATA__[/]")

    time.sleep(SCRAPLING_REQUEST_DELAY)
    return products[:10]


# --- Agent-Facing Tools ---


def search_walmart(query: str) -> list[dict]:
    """Search Walmart for grocery products by name. Returns top 3 cheapest matches.

    Args:
        query: The grocery item to search for, e.g. "bananas" or "milk gallon".

    Returns:
        List of up to 3 product dicts with name and price, sorted cheapest first.
    """
    products: list[WalmartProduct] = []

    # Try Scrapling (stealth browser) first
    try:
        products = _scrape_walmart_search(query)
        if not products:
            console.print("[yellow]Scrapling returned no results, falling back to Jina[/]")
            products = []
    except ImportError:
        console.print("[yellow]Scrapling not installed, using Jina[/]")
    except Exception as e:
        console.print(f"[yellow]Scrapling failed ({e}), falling back to Jina[/]")

    # Fall back to Jina if needed
    if not products:
        products = _search_walmart_jina(query)

    if not products:
        return []

    # Sort by price (cheapest first), push items without price to the end
    priced = [p for p in products if p.price is not None and p.price > 0]
    priced.sort(key=lambda p: p.price)

    # Store full data for Rich table display (main.py reads _last_full_results)
    top = priced[:5] if priced else products[:3]
    search_walmart._last_full_results = [p.model_dump() for p in top]

    # Return slim payload for the model — only what it needs to reason
    return [
        {"name": p.name, "price": p.price}
        for p in top[:3]
    ]


# Attribute to store full results for display (read by main.py)
search_walmart._last_full_results = []


def fetch_notes_list() -> list[dict]:
    """List all Apple Notes. Returns list of notes with index, folder, and title.

    Returns:
        List of dicts with 'index', 'folder', 'title' keys.
    """
    try:
        result = subprocess.run(
            ["memo", "notes"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        console.print(
            "[bold red]Error:[/] memo CLI not found. "
            "Install it: brew tap antoniorodr/memo && brew install antoniorodr/memo/memo"
        )
        return []

    notes = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line or not line[0].isdigit():
            continue
        dot_pos = line.find(".")
        if dot_pos == -1:
            continue
        try:
            index = int(line[:dot_pos])
        except ValueError:
            continue
        rest = line[dot_pos + 1:].strip()
        dash_pos = rest.find(" - ")
        if dash_pos != -1:
            folder = rest[:dash_pos].strip()
            title = rest[dash_pos + 3:].strip()
        else:
            folder = ""
            title = rest
        notes.append({"index": index, "folder": folder, "title": title})

    return notes


def fetch_note_content(note_index: int) -> str:
    """Read the full content of a specific Apple Note by its index number.

    Args:
        note_index: The 1-based index of the note from the notes list.

    Returns:
        The note content as plain text.
    """
    try:
        result = subprocess.run(
            ["memo", "notes", "-v", str(note_index)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        content = result.stdout.strip()
        # Detect memo error messages (e.g. "Note 999 not found.")
        if content.lower().startswith("note") and "not found" in content.lower():
            return ""
        return content
    except FileNotFoundError:
        console.print(
            "[bold red]Error:[/] memo CLI not found. "
            "Install it: brew tap antoniorodr/memo && brew install antoniorodr/memo/memo"
        )
        return ""
    except subprocess.TimeoutExpired:
        console.print(
            "[bold red]Error:[/] memo timed out reading note. "
            "Apple Notes may be slow — try again."
        )
        return ""


def fetch_notes_from_folder(folder: str) -> list[dict]:
    """Fetch notes from a specific Apple Notes folder via Memo CLI.

    Args:
        folder: The folder name to filter by.

    Returns:
        A list of dicts with 'index' and 'title' for each note in the folder.
    """
    try:
        result = subprocess.run(
            ["memo", "notes", "-f", folder],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError:
        console.print("[bold red]Error:[/] memo CLI not found.")
        return []

    notes = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line or not line[0].isdigit():
            continue
        dot_pos = line.find(".")
        if dot_pos == -1:
            continue
        try:
            index = int(line[:dot_pos])
        except ValueError:
            continue
        rest = line[dot_pos + 1:].strip()
        dash_pos = rest.find(" - ")
        title = rest[dash_pos + 3:].strip() if dash_pos != -1 else rest
        notes.append({"index": index, "title": title})

    return notes


def notify_user(message: str, method: str = "email") -> str:
    """Send a notification to the user about their grocery list results.

    Args:
        message: The notification message content to send.
        method: Notification method — "email", "calendar", or "all".

    Returns:
        A confirmation string describing what was sent.
    """
    # TODO: Phase 2 — integrate Gmail API and Google Calendar API
    confirmations = []

    if method in ("email", "all"):
        console.print(
            f"[yellow][Phase 2][/] Would send email with message: {message[:100]}..."
        )
        confirmations.append("email queued")

    if method in ("calendar", "all"):
        console.print(
            f"[yellow][Phase 2][/] Would create calendar event: "
            f"'Walmart Grocery Delivery' at {datetime.now().isoformat()}"
        )
        confirmations.append("calendar event queued")

    return f"Notification sent via {', '.join(confirmations)}" if confirmations else "No notification method selected"
