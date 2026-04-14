"""
Failure taxonomy grouped bar chart.

Reads from .eval_results/traces.db and produces a grouped bar chart showing
failure mode distribution by query type.

Usage:
    python scripts/viz_failure_taxonomy.py
    python scripts/viz_failure_taxonomy.py --db path/to/traces.db
    python scripts/viz_failure_taxonomy.py --out docs/charts/failure_taxonomy.png

Output: docs/charts/failure_taxonomy.png
"""
import sys
import os
import argparse
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(_PROJECT_ROOT, ".eval_results", "traces.db")
DEFAULT_OUT = os.path.join(_PROJECT_ROOT, "docs", "charts", "failure_taxonomy.png")

FAILURE_MODES = [
    "success",
    "catalog_gap",
    "impossible_constraints",
    "no_results",
    "hallucination",
    "citation_error",
    "missing_spec_failure",
    "constraint_violation",
    "out_of_stock_presented",
    "ranking_failure",
]

QUERY_TYPES = [
    "constraint_heavy",
    "vague",
    "comparison",
    "availability",
    "multi_turn",
    "adversarial",
]

# Colors assigned alphabetically by mode name → ROYGBIV + brown.
# Alphabetical order: catalog_gap, citation_error, constraint_violation,
#   hallucination, impossible_constraints, missing_spec_failure,
#   no_results, out_of_stock_presented, ranking_failure, success
_MODE_COLORS = {
    "catalog_gap":            "#c0392b",  # R — red
    "citation_error":         "#d35400",  # O — orange
    "constraint_violation":   "#b8860b",  # Y — dark mustard
    "hallucination":          "#d4a017",  # Y — gold/amber (distinct from mustard)
    "impossible_constraints": "#2980b9",  # B — blue
    "missing_spec_failure":   "#5b2d8e",  # I — indigo
    "no_results":             "#7d3c98",  # V — violet
    "out_of_stock_presented": "#6d4c41",  # brown
    "ranking_failure":        "#7f8c8d",  # grey (beyond ROYGBIV+brown)
    "success":                "#27ae60",  # G — green
}


def _load_from_db(db_path: str) -> dict:
    """
    Load failure counts keyed by (query_type, failure_mode) from SQLite.
    Returns {query_type: {failure_mode: count}}.
    """
    if not os.path.exists(db_path):
        return {}

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT query_type, failure_mode FROM traces "
            "WHERE query_type IS NOT NULL AND failure_mode IS NOT NULL"
        ).fetchall()

    counts: dict = {}
    for qt, fm in rows:
        counts.setdefault(qt, {})
        counts[qt][fm] = counts[qt].get(fm, 0) + 1
    return counts


def _seed_illustrative_data() -> dict:
    """
    # SEED: illustrative data — used when the real DB has insufficient traces
    # (<2 rows per query type). These values represent plausible failure
    # distributions for a shopping agent at initial deployment. Not real data.
    """
    return {
        "constraint_heavy": {
            "success": 8, "catalog_gap": 2, "impossible_constraints": 2,
            "no_results": 1, "missing_spec_failure": 1,
        },
        "vague": {
            "success": 6, "hallucination": 3, "no_results": 2,
            "ranking_failure": 1, "catalog_gap": 1,
        },
        "comparison": {
            "success": 5, "hallucination": 2, "citation_error": 2,
            "ranking_failure": 1, "no_results": 1,
        },
        "availability": {
            "success": 7, "out_of_stock_presented": 3, "no_results": 2,
            "catalog_gap": 1,
        },
        "multi_turn": {
            "success": 4, "no_results": 3, "missing_spec_failure": 2,
            "constraint_violation": 1, "impossible_constraints": 1,
        },
        "adversarial": {
            "success": 3, "hallucination": 4, "citation_error": 2,
            "no_results": 1,
        },
    }


def _normalize_query_type(qt: str) -> str:
    """Map raw query_type strings from DB to display bucket names."""
    _MAP = {
        "single_turn": "constraint_heavy",
        "multi_turn": "multi_turn",
        "edge_case": "comparison",
        "out_of_stock": "availability",
        "adversarial": "adversarial",
        "vague": "vague",
        "comparison": "comparison",
        "constraint_heavy": "constraint_heavy",
        "availability": "availability",
        "availability_sensitive": "availability",
    }
    return _MAP.get(qt, "constraint_heavy")


def build_data(db_path: str) -> tuple[dict, bool]:
    """
    Return (data, is_seeded).
    data = {query_type: {failure_mode: count}}
    is_seeded = True if synthetic data was used to fill gaps.
    """
    raw = _load_from_db(db_path)

    # Remap raw query types to display buckets
    bucketed: dict = {}
    for qt, counts in raw.items():
        bucket = _normalize_query_type(qt)
        for fm, cnt in counts.items():
            bucketed.setdefault(bucket, {})
            bucketed[bucket][fm] = bucketed[bucket].get(fm, 0) + cnt

    # Check coverage — need at least 2 rows per bucket to be meaningful
    covered = {qt for qt, counts in bucketed.items() if sum(counts.values()) >= 2}
    needs_seed = len(covered) < len(QUERY_TYPES)

    if needs_seed:
        seed = _seed_illustrative_data()
        # Merge: real data wins where present, seed fills the gaps
        for qt in QUERY_TYPES:
            if qt not in covered:
                bucketed[qt] = seed.get(qt, {"success": 5, "no_results": 2})

    return bucketed, needs_seed


def plot(data: dict, out_path: str, is_seeded: bool) -> None:
    modes_present = [m for m in FAILURE_MODES if any(
        m in data.get(qt, {}) for qt in QUERY_TYPES
    )]

    x = np.arange(len(QUERY_TYPES))
    bar_width = 0.8 / max(len(modes_present), 1)

    fig, ax = plt.subplots(figsize=(14, 6))

    for i, mode in enumerate(modes_present):
        failure_rates = []
        for qt in QUERY_TYPES:
            counts = data.get(qt, {})
            total = sum(counts.values())
            rate = counts.get(mode, 0) / total if total else 0.0
            failure_rates.append(rate)

        offset = (i - len(modes_present) / 2 + 0.5) * bar_width
        color = _MODE_COLORS.get(mode, "#9e9e9e")
        ax.bar(x + offset, failure_rates, bar_width * 0.9,
               label=mode, color=color, alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels(QUERY_TYPES, rotation=15, ha="right", fontsize=10)
    ax.set_ylabel("Failure Rate", fontsize=11)
    ax.set_xlabel("Query Type", fontsize=11)
    title = "Failure Mode Distribution by Query Type"
    if is_seeded:
        title += " (illustrative — insufficient real traces)"
    ax.set_title(title, fontsize=13)
    ax.set_ylim(0, 1.05)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", fontsize=8, ncol=2, framealpha=0.85)

    plt.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plt.savefig(out_path, dpi=150)
    plt.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DEFAULT_DB,
                        help="Path to traces.db")
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help="Output PNG path")
    args = parser.parse_args()

    data, is_seeded = build_data(args.db)
    plot(data, args.out, is_seeded)

    if is_seeded:
        print(
            "NOTE: Insufficient real traces — illustrative seed data "
            "used for some query types."
        )
    print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()
