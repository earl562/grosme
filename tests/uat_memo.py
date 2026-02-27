"""UAT: Memo (Apple Notes) tool tests for the grosme agent."""

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


def test_list_notes() -> dict:
    """Test: list Apple Notes — agent should call fetch_notes_list."""
    print("\n--- Test: List Notes ---")
    final, results = run_conversation(
        "Show me my Apple Notes.",
        TOOLS,
        AVAILABLE_FUNCTIONS,
        verbose=True,
    )
    list_calls = _check_tool_called(results, "fetch_notes_list")

    passed = list_calls >= 1
    print(f"  fetch_notes_list calls: {list_calls}")
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    return {"name": "list_notes", "passed": passed, "list_calls": list_calls}


def test_read_note_and_search() -> dict:
    """Test: read a specific note and search for items."""
    print("\n--- Test: Read Note + Search ---")
    final, results = run_conversation(
        "Read note #2 and find any grocery items in it. "
        "Search Walmart for each grocery item you find.",
        TOOLS,
        AVAILABLE_FUNCTIONS,
        verbose=True,
    )
    read_calls = _check_tool_called(results, "fetch_note_content")
    search_calls = _check_tool_called(results, "search_walmart")

    # Agent should read the note at minimum
    passed = read_calls >= 1
    print(f"  fetch_note_content calls: {read_calls}")
    print(f"  search_walmart calls: {search_calls}")
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    return {
        "name": "read_note_and_search",
        "passed": passed,
        "read_calls": read_calls,
        "search_calls": search_calls,
    }


def test_browse_and_search() -> dict:
    """Test: browse notes, find a grocery list, and search."""
    print("\n--- Test: Browse + Search ---")
    final, results = run_conversation(
        "Look through my Apple Notes for a grocery list and search Walmart "
        "for everything on it.",
        TOOLS,
        AVAILABLE_FUNCTIONS,
        verbose=True,
    )
    list_calls = _check_tool_called(results, "fetch_notes_list")
    read_calls = _check_tool_called(results, "fetch_note_content")

    # Agent should at least list notes and read one
    passed = list_calls >= 1 and read_calls >= 1
    print(f"  fetch_notes_list calls: {list_calls}")
    print(f"  fetch_note_content calls: {read_calls}")
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    return {
        "name": "browse_and_search",
        "passed": passed,
        "list_calls": list_calls,
        "read_calls": read_calls,
    }


def test_no_groceries_found() -> dict:
    """Test: note with no grocery items — agent should say nothing found."""
    print("\n--- Test: No Groceries Found ---")
    final, results = run_conversation(
        "Read note #1 and find grocery items. If there are no grocery items, "
        "let me know. Search Walmart only for actual grocery items.",
        TOOLS,
        AVAILABLE_FUNCTIONS,
        verbose=True,
    )
    read_calls = _check_tool_called(results, "fetch_note_content")

    # Agent should at least attempt to read the note
    passed = read_calls >= 1
    print(f"  fetch_note_content calls: {read_calls}")
    print(f"  final response length: {len(final)}")
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    return {"name": "no_groceries_found", "passed": passed, "read_calls": read_calls}


ALL_TESTS = [
    test_list_notes,
    test_read_note_and_search,
    test_browse_and_search,
    test_no_groceries_found,
]


def run_all() -> list[dict]:
    """Run all memo UAT tests and return results."""
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
    print("\n=== Memo UAT Summary ===")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['name']}")
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    print(f"\n{passed}/{total} tests passed")
