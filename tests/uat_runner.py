"""Unified UAT runner for grosme agent tests."""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser(description="Run grosme UAT tests")
    parser.add_argument("--query", action="store_true", help="Run query tests only")
    parser.add_argument("--memo", action="store_true", help="Run memo tests only")
    args = parser.parse_args()

    # Default: run all if no flag specified
    run_query = args.query or (not args.query and not args.memo)
    run_memo = args.memo or (not args.query and not args.memo)

    all_results = []

    if run_query:
        print("=" * 60)
        print("  QUERY TESTS")
        print("=" * 60)
        from tests.uat_query import run_all as run_query_tests

        all_results.extend(run_query_tests())

    if run_memo:
        print("\n" + "=" * 60)
        print("  MEMO TESTS")
        print("=" * 60)
        from tests.uat_memo import run_all as run_memo_tests

        all_results.extend(run_memo_tests())

    # Final summary
    print("\n" + "=" * 60)
    print("  FINAL SUMMARY")
    print("=" * 60)
    for r in all_results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['name']}")

    total = len(all_results)
    passed = sum(1 for r in all_results if r["passed"])
    failed = total - passed
    print(f"\n  {passed}/{total} passed, {failed} failed")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
