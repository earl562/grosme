"""Walmart product search and matching orchestrator."""

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from model import rank_products
from models import GroceryItem, GroceryList, MatchedItem, WalmartProduct
from tools import search_walmart

console = Console()


def build_search_query(item: GroceryItem) -> str:
    """Build an optimized Walmart search query from a grocery item.

    Args:
        item: The grocery item to build a query for.

    Returns:
        A search query string tailored for Walmart product search.
    """
    parts = [item.name]
    if item.quantity > 1 and item.unit:
        parts.append(f"{item.quantity} {item.unit}")
    elif item.unit:
        parts.append(item.unit)
    return " ".join(parts)


def search_item(item: GroceryItem) -> MatchedItem:
    """Search Walmart for a single grocery item and find the best match.

    Args:
        item: The grocery item to search for.

    Returns:
        A MatchedItem with the best product match and confidence score.
    """
    query = build_search_query(item)
    products = search_walmart(query)

    if not products:
        return MatchedItem(
            grocery_item=item,
            matched_product=None,
            confidence=0.0,
            alternatives=[],
            status="not_found",
        )

    # Prepare product data for LLM ranking
    products_for_llm = [
        {
            "index": i,
            "name": p.name,
            "price": p.price,
            "brand": p.brand,
            "size": p.size,
            "availability": p.availability,
        }
        for i, p in enumerate(products)
    ]

    ranking = rank_products(item, products_for_llm)

    best_idx = int(ranking.get("best_match_index", 0))
    confidence = float(ranking.get("confidence", 0.5))

    # Clamp index to valid range
    best_idx = max(0, min(best_idx, len(products) - 1))

    best_product = products[best_idx]
    alternatives = [p for i, p in enumerate(products) if i != best_idx]

    status = "matched" if confidence >= 0.7 else "partial"

    return MatchedItem(
        grocery_item=item,
        matched_product=best_product,
        confidence=confidence,
        alternatives=alternatives,
        status=status,
    )


def process_grocery_list(items: list[GroceryItem]) -> GroceryList:
    """Process all grocery items through the search-and-match pipeline.

    Args:
        items: The list of grocery items to search for.

    Returns:
        A completed GroceryList with all match results.
    """
    matched_items: list[MatchedItem] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Searching Walmart...", total=len(items))

        for item in items:
            progress.update(task, description=f"Searching: {item.name}...")
            result = search_item(item)
            matched_items.append(result)
            progress.advance(task)

    total_cost = sum(
        m.matched_product.price
        for m in matched_items
        if m.matched_product and m.matched_product.price
    )

    return GroceryList(
        items=matched_items,
        total_estimated_cost=total_cost,
    )
