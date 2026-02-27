"""UAT: Direct query tests for the grosme agent."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import run_conversation
from tools import (
    fetch_note_content,
    fetch_notes_from_folder,
    fetch_notes_list,
    notify_user,
    search_walmart,
)

TOOLS = [search_walmart, fetch_notes_list, fetch_note_content, notify_user]
AVAILABLE_FUNCTIONS = {
    "search_walmart": search_walmart,
    "fetch_notes_list": fetch_notes_list,
    "fetch_note_content": fetch_note_content,
    "fetch_notes_from_folder": fetch_notes_from_folder,
    "notify_user": notify_user,
}


def _check_tool_called(tool_results: list[dict], tool_name: str) -> int:
    """Count how many times a specific tool was called."""
    return sum(1 for r in tool_results if r["tool"] == tool_name)


def _check_products_have_prices(tool_results: list[dict]) -> bool:
    """Check if at least one search_walmart result has a price."""
    for r in tool_results:
        if r["tool"] == "search_walmart" and r["result"]:
            for product in r["result"]:
                if isinstance(product, dict) and product.get("price"):
                    return True
    return False


def test_single_item() -> dict:
    """Test: single item search — 'bananas'."""
    print("\n--- Test: Single Item (bananas) ---")
    final, results = run_conversation(
        "Here is my grocery list: bananas\n\nSearch Walmart for each item.",
        TOOLS,
        AVAILABLE_FUNCTIONS,
        verbose=True,
    )
    search_calls = _check_tool_called(results, "search_walmart")
    has_prices = _check_products_have_prices(results)
    mentions_item = "banana" in final.lower()

    passed = search_calls >= 1 and has_prices
    print(f"  search_walmart calls: {search_calls}")
    print(f"  has prices: {has_prices}")
    print(f"  mentions item: {mentions_item}")
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    return {"name": "single_item", "passed": passed, "search_calls": search_calls}


def test_multiple_items() -> dict:
    """Test: multiple items — 'milk, eggs, bread, chicken breast'."""
    print("\n--- Test: Multiple Items ---")
    final, results = run_conversation(
        "Here is my grocery list: milk, eggs, bread, chicken breast\n\n"
        "Search Walmart for each item individually.",
        TOOLS,
        AVAILABLE_FUNCTIONS,
        verbose=True,
    )
    search_calls = _check_tool_called(results, "search_walmart")
    has_prices = _check_products_have_prices(results)

    passed = search_calls >= 4 and has_prices
    print(f"  search_walmart calls: {search_calls}")
    print(f"  has prices: {has_prices}")
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    return {"name": "multiple_items", "passed": passed, "search_calls": search_calls}


def test_quantity_and_unit() -> dict:
    """Test: quantity + unit — '2 gallons of milk'."""
    print("\n--- Test: Quantity + Unit (2 gallons of milk) ---")
    final, results = run_conversation(
        "Here is my grocery list: 2 gallons of milk\n\n"
        "Search Walmart for each item.",
        TOOLS,
        AVAILABLE_FUNCTIONS,
        verbose=True,
    )
    search_calls = _check_tool_called(results, "search_walmart")
    has_prices = _check_products_have_prices(results)

    # Check that the search query includes milk-related terms
    queries = [r["args"].get("query", "").lower() for r in results if r["tool"] == "search_walmart"]
    milk_searched = any("milk" in q for q in queries)

    passed = search_calls >= 1 and milk_searched
    print(f"  search_walmart calls: {search_calls}")
    print(f"  queries: {queries}")
    print(f"  milk searched: {milk_searched}")
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    return {"name": "quantity_unit", "passed": passed, "search_calls": search_calls}


def test_misspelled_item() -> dict:
    """Test: misspelled item — 'advocados'."""
    print("\n--- Test: Misspelled Item (advocados) ---")
    final, results = run_conversation(
        "Here is my grocery list: advocados\n\n"
        "Search Walmart for each item. Fix any spelling mistakes.",
        TOOLS,
        AVAILABLE_FUNCTIONS,
        verbose=True,
    )
    search_calls = _check_tool_called(results, "search_walmart")
    queries = [r["args"].get("query", "").lower() for r in results if r["tool"] == "search_walmart"]

    # Agent should correct to avocado
    corrected = any("avocado" in q for q in queries)

    passed = search_calls >= 1
    print(f"  search_walmart calls: {search_calls}")
    print(f"  queries: {queries}")
    print(f"  corrected spelling: {corrected}")
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    return {"name": "misspelled_item", "passed": passed, "corrected": corrected}


def test_ambiguous_item() -> dict:
    """Test: ambiguous item — 'chips'."""
    print("\n--- Test: Ambiguous Item (chips) ---")
    final, results = run_conversation(
        "Here is my grocery list: chips\n\n"
        "Search Walmart for each item.",
        TOOLS,
        AVAILABLE_FUNCTIONS,
        verbose=True,
    )
    search_calls = _check_tool_called(results, "search_walmart")
    has_prices = _check_products_have_prices(results)

    passed = search_calls >= 1
    print(f"  search_walmart calls: {search_calls}")
    print(f"  has prices: {has_prices}")
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    return {"name": "ambiguous_item", "passed": passed, "search_calls": search_calls}


ALL_TESTS = [
    test_single_item,
    test_multiple_items,
    test_quantity_and_unit,
    test_misspelled_item,
    test_ambiguous_item,
]


def run_all() -> list[dict]:
    """Run all query UAT tests and return results."""
    results = []
    for test_fn in ALL_TESTS:
        try:
            result = test_fn()
        except Exception as e:
            print(f"  ERROR: {e}")
            result = {"name": test_fn.__name__, "passed": False, "error": str(e)}
        results.append(result)
    return results


if __name__ == "__main__":
    results = run_all()
    print("\n=== Query UAT Summary ===")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['name']}")
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    print(f"\n{passed}/{total} tests passed")
