"""
Run-over-run variance test for the shopping agent.

Runs the same query N times and reports per-metric mean, std dev, and
coefficient of variation (CV = std / mean). High CV means a metric is
non-deterministic enough that single-run numbers can't be trusted for
detecting real signal vs. noise in A/A' comparisons.

Also reports:
  product_set_stability   Jaccard similarity of ranked product ID sets across
                          all N runs (1.0 = identical every run, 0.0 = fully
                          different)
  failure_mode_consistency  True if every run produces the same failure mode

Usage:
    python scripts/stability_test.py q_001           # 3 runs (default)
    python scripts/stability_test.py q_001 --n 5     # 5 runs
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # noqa: E402
load_dotenv()

from langfuse import get_client  # noqa: E402
from evals.metrics.stability import (  # noqa: E402
    run_stability_test, print_stability_report
)


def main():
    parser = argparse.ArgumentParser(
        description="Run-over-run variance test for a single canonical query"
    )
    parser.add_argument("query_id", help="Canonical query ID (e.g. q_001)")
    parser.add_argument(
        "--n", type=int, default=3, help="Number of runs (default: 3)"
    )
    parser.add_argument(
        "--version", default="v1",
        help="Agent version tag for A/A' comparison in Langfuse (default: v1)"
    )
    args = parser.parse_args()

    report = run_stability_test(args.query_id, args.n, args.version)
    print_stability_report(report)
    get_client().flush()


if __name__ == "__main__":
    main()
