"""Benchmark: run a known grocery list through search_walmart and score results."""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import search_walmart

# Ground truth: query → what we expect to see in the top result.
# "brand" is the brand we asked for (None if generic).
# "keywords" are words that MUST appear in the matched product name.
TEST_ITEMS = [
    {"query": "Eggland's Best Eggs 18 ct", "brand": "Eggland's Best", "keywords": ["egg"]},
    {"query": "Driscoll's Strawberries 1 lb", "brand": "Driscoll's", "keywords": ["strawberr"]},
    {"query": "Whole Milk Gallon", "brand": None, "keywords": ["milk", "gallon"]},
    {"query": "Tyson Chicken Breast", "brand": "Tyson", "keywords": ["chicken"]},
    {"query": "Bananas", "brand": None, "keywords": ["banana"]},
    {"query": "Great Value Butter", "brand": "Great Value", "keywords": ["butter"]},
    {"query": "Hillshire Farm Deli Meat", "brand": "Hillshire Farm", "keywords": ["deli", "meat"]},
    {"query": "Barilla Spaghetti", "brand": "Barilla", "keywords": ["spaghetti"]},
    {"query": "InnovAsian Orange Chicken", "brand": "InnovAsian", "keywords": ["orange", "chicken"]},
    {"query": "Outshine Fruit Bars", "brand": "Outshine", "keywords": ["fruit", "bar"]},
    {"query": "Bread", "brand": None, "keywords": ["bread"]},
    {"query": "Bacon", "brand": None, "keywords": ["bacon"]},
    {"query": "Frozen Broccoli", "brand": None, "keywords": ["broccoli"]},
    {"query": "Pork Chops", "brand": None, "keywords": ["pork"]},
    {"query": "Blueberries", "brand": None, "keywords": ["blueberr"]},
    {"query": "Cheddar Cheese", "brand": None, "keywords": ["cheddar", "cheese"]},
    {"query": "Orange Juice", "brand": None, "keywords": ["orange", "juice"]},
    {"query": "Ground Beef", "brand": None, "keywords": ["ground", "beef"]},
    {"query": "Rice", "brand": None, "keywords": ["rice"]},
    {"query": "Pasta Sauce", "brand": None, "keywords": ["sauce"]},
]


def score_result(item: dict, result: list[dict]) -> dict:
    """Score a single search result against expected values."""
    if not result:
        return {"status": "not_found", "detail": "no results returned"}

    top = result[0]
    name = (top.get("name") or "").lower()

    # Check keywords
    missing_keywords = [k for k in item["keywords"] if k.lower() not in name]
    if missing_keywords:
        return {
            "status": "wrong_product",
            "detail": f"missing keywords: {missing_keywords}, got: {top.get('name', '')[:60]}",
        }

    # Check brand if one was specified
    if item["brand"]:
        # Pull full results to check brand field
        full = getattr(search_walmart, "_last_full_results", [])
        top_full = full[0] if full else {}
        matched_brand = top_full.get("brand", "") or ""

        if item["brand"].lower() not in matched_brand.lower() and item["brand"].lower() not in name:
            return {
                "status": "wrong_brand",
                "detail": f"wanted {item['brand']}, got brand='{matched_brand}', name='{top.get('name', '')[:60]}'",
            }

    # Check price exists
    if not top.get("price"):
        return {"status": "no_price", "detail": f"matched but no price: {top.get('name', '')[:60]}"}

    return {"status": "correct", "detail": top.get("name", "")[:60]}


def run_benchmark():
    print(f"grosme accuracy benchmark — {len(TEST_ITEMS)} items")
    print(f"started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    results = []
    for i, item in enumerate(TEST_ITEMS, 1):
        print(f"\n[{i}/{len(TEST_ITEMS)}] {item['query']}")
        start = time.time()
        try:
            search_result = search_walmart(item["query"])
        except Exception as e:
            search_result = []
            print(f"  ERROR: {e}")
        elapsed = time.time() - start

        score = score_result(item, search_result)
        score["query"] = item["query"]
        score["expected_brand"] = item["brand"]
        score["elapsed_s"] = round(elapsed, 1)

        if search_result:
            score["matched_name"] = search_result[0].get("name", "")[:60]
            score["matched_price"] = search_result[0].get("price")
        else:
            score["matched_name"] = None
            score["matched_price"] = None

        icon = {"correct": "+", "wrong_brand": "~", "wrong_product": "X", "not_found": "?", "no_price": "$"}
        print(f"  [{icon.get(score['status'], '?')}] {score['status']} — {score['detail']} ({elapsed:.1f}s)")
        results.append(score)

    # Summary
    print("\n" + "=" * 70)
    total = len(results)
    correct = sum(1 for r in results if r["status"] == "correct")
    wrong_brand = sum(1 for r in results if r["status"] == "wrong_brand")
    wrong_product = sum(1 for r in results if r["status"] == "wrong_product")
    not_found = sum(1 for r in results if r["status"] == "not_found")
    no_price = sum(1 for r in results if r["status"] == "no_price")
    avg_time = sum(r["elapsed_s"] for r in results) / total if total else 0

    print(f"\nRESULTS: {correct}/{total} correct ({correct/total*100:.0f}%)")
    print(f"  correct:       {correct}")
    print(f"  wrong brand:   {wrong_brand}")
    print(f"  wrong product: {wrong_product}")
    print(f"  not found:     {not_found}")
    print(f"  no price:      {no_price}")
    print(f"  avg time/item: {avg_time:.1f}s")

    # Save to file
    output = {
        "timestamp": datetime.now().isoformat(),
        "total": total,
        "correct": correct,
        "wrong_brand": wrong_brand,
        "wrong_product": wrong_product,
        "not_found": not_found,
        "no_price": no_price,
        "accuracy_pct": round(correct / total * 100, 1) if total else 0,
        "avg_time_s": round(avg_time, 1),
        "items": results,
    }

    out_path = Path(__file__).parent / "results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\nFull results saved to {out_path}")

    return output


if __name__ == "__main__":
    run_benchmark()
