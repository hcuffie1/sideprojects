"""
Metric movement over time chart.

Shows how key eval metrics change across tagged versions. Pulls from Langfuse
if credentials are present; falls back to the local SQLite traces.db.

Usage:
    python scripts/viz_metric_movement.py
    python scripts/viz_metric_movement.py --out docs/charts/metric_movement.png
    python scripts/viz_metric_movement.py --source sqlite  # force SQLite

Output: docs/charts/metric_movement.png
"""
import sys
import os
import argparse
import json
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(_PROJECT_ROOT, ".eval_results", "traces.db")
DEFAULT_OUT = os.path.join(_PROJECT_ROOT, "docs", "charts", "metric_movement.png")

METRICS = ["top1_valid_rate", "constraint_satisfaction_rate",
           "avg_groundedness", "avg_citation_accuracy"]

_METRIC_COLORS = {
    "top1_valid_rate": "#1565c0",
    "constraint_satisfaction_rate": "#2e7d32",
    "avg_groundedness": "#e65100",
    "avg_citation_accuracy": "#6a1b9a",
}

_METRIC_LABELS = {
    "top1_valid_rate": "Top-1 Valid Rate",
    "constraint_satisfaction_rate": "Constraint Sat. Rate",
    "avg_groundedness": "Avg Groundedness",
    "avg_citation_accuracy": "Avg Citation Accuracy",
}


# ── Langfuse source ────────────────────────────────────────────────────────────

def _load_from_langfuse() -> dict | None:
    """
    Fetch per-version metric averages from Langfuse scores API.
    Returns {version: {metric: value}} or None if credentials missing.
    """
    pub = os.getenv("LANGFUSE_PUBLIC_KEY")
    sec = os.getenv("LANGFUSE_SECRET_KEY")
    if not pub or not sec:
        return None

    try:
        from langfuse import get_client
        client = get_client()

        # Fetch recent traces and group by agent_version metadata
        # Langfuse Python SDK: client.api.traces.list()
        traces_page = client.api.traces.list(limit=500)
        traces = getattr(traces_page, "data", []) or []

        version_data: dict = {}
        for trace in traces:
            meta = getattr(trace, "metadata", {}) or {}
            version = meta.get("agent_version") or meta.get("version")
            if not version:
                continue

            scores = getattr(trace, "scores", []) or []
            score_map = {s.name: s.value for s in scores if s.value is not None}

            # Map Langfuse score names to our metric names
            _SCORE_TO_METRIC = {
                "top1_valid": "top1_valid_rate",
                "constraint_satisfaction": "constraint_satisfaction_rate",
                "groundedness": "avg_groundedness",
            }
            for score_name, metric in _SCORE_TO_METRIC.items():
                if score_name in score_map:
                    version_data.setdefault(version, {}).setdefault(metric, [])
                    version_data[version][metric].append(score_map[score_name])

        if not version_data:
            return None

        # Average across traces per version
        return {
            v: {m: sum(vals) / len(vals) for m, vals in metrics.items()}
            for v, metrics in version_data.items()
        }

    except Exception:
        return None


# ── SQLite source ──────────────────────────────────────────────────────────────

def _load_from_sqlite(db_path: str) -> dict:
    """
    Load per-version metrics from traces.db using the version stored in
    metrics_json. Returns {version: {metric: value}}.
    """
    if not os.path.exists(db_path):
        return {}

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT metrics_json, avg_groundedness, top1_valid "
            "FROM traces WHERE metrics_json IS NOT NULL"
        ).fetchall()

    version_data: dict = {}
    for metrics_json, avg_g, top1 in rows:
        try:
            meta = json.loads(metrics_json)
        except (json.JSONDecodeError, TypeError):
            continue
        version = meta.get("agent_version") or meta.get("version")
        if not version:
            continue
        version_data.setdefault(version, {"avg_groundedness": [], "top1_valid_rate": []})
        if avg_g is not None:
            version_data[version]["avg_groundedness"].append(avg_g)
        if top1 is not None:
            version_data[version]["top1_valid_rate"].append(float(top1))

    return {
        v: {m: sum(vals) / len(vals) for m, vals in metrics.items() if vals}
        for v, metrics in version_data.items()
    }


# ── Seed ───────────────────────────────────────────────────────────────────────

def _seed_illustrative_data() -> dict:
    """
    # SEED: illustrative data — used when fewer than 3 real version tags
    # exist in the DB or Langfuse. Represents a plausible improvement trend
    # with one regression (v3) and recovery (v4+). Not real measurements.
    """
    return {
        "v1_baseline": {
            "top1_valid_rate": 0.61,
            "constraint_satisfaction_rate": 0.68,
            "avg_groundedness": 0.70,
            "avg_citation_accuracy": None,
        },
        "v2_enriched_catalog": {
            "top1_valid_rate": 0.61,
            "constraint_satisfaction_rate": 0.78,
            "avg_groundedness": 0.70,
            "avg_citation_accuracy": None,
        },
        "v3_prompt_fields": {
            "top1_valid_rate": 0.74,
            "constraint_satisfaction_rate": 0.81,
            "avg_groundedness": 0.65,   # regression
            "avg_citation_accuracy": 0.72,
        },
        "v4_groundedness_boolean": {
            "top1_valid_rate": 0.78,
            "constraint_satisfaction_rate": 0.84,
            "avg_groundedness": 0.76,
            "avg_citation_accuracy": 0.79,
        },
        "v5_citation_baseline": {
            "top1_valid_rate": 0.83,
            "constraint_satisfaction_rate": 0.88,
            "avg_groundedness": 0.81,
            "avg_citation_accuracy": 0.85,
        },
    }


def _version_sort_key(v: str) -> tuple:
    """Sort version tags: vN* numerically first, then weekly_YYYYMMDD, then alpha."""
    if v.startswith("v") and len(v) > 1 and v[1].isdigit():
        parts = v.split("_", 1)
        try:
            return (0, int(parts[0][1:]), parts[1] if len(parts) > 1 else "")
        except ValueError:
            pass
    if v.startswith("weekly_"):
        return (1, 0, v)
    return (2, 0, v)


def build_data(db_path: str, force_sqlite: bool = False) -> tuple[dict, bool]:
    """Return (data, is_seeded) where data = {version: {metric: value}}."""
    data: dict = {}

    if not force_sqlite:
        data = _load_from_langfuse() or {}

    if not data:
        data = _load_from_sqlite(db_path)

    real_versions = len(data)
    is_seeded = real_versions < 3

    if is_seeded:
        seed = _seed_illustrative_data()
        # Prepend seed versions; real data overlays if version key matches
        merged = {**seed, **data}
        data = merged

    return data, is_seeded


def plot(data: dict, out_path: str, is_seeded: bool) -> None:
    versions = sorted(data.keys(), key=_version_sort_key)

    fig, ax = plt.subplots(figsize=(12, 5))

    for metric in METRICS:
        ys = [data[v].get(metric) for v in versions]
        # Only plot points where the metric exists
        xs_plot = [i for i, y in enumerate(ys) if y is not None]
        ys_plot = [ys[i] for i in xs_plot]
        if not ys_plot:
            continue
        color = _METRIC_COLORS[metric]
        label = _METRIC_LABELS[metric]
        ax.plot(xs_plot, ys_plot, marker="o", linewidth=2,
                color=color, label=label)

    ax.set_xticks(range(len(versions)))
    ax.set_xticklabels(versions, rotation=20, ha="right", fontsize=9)
    ax.set_ylabel("Metric Value", fontsize=11)
    ax.set_xlabel("Eval Version", fontsize=11)
    title = "Metric Movement Across Eval Versions"
    if is_seeded:
        title += " (illustrative — insufficient real version history)"
    ax.set_title(title, fontsize=13)
    ax.set_ylim(0, 1.05)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", fontsize=9, framealpha=0.85)

    plt.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plt.savefig(out_path, dpi=150)
    plt.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--source", choices=["auto", "sqlite"], default="auto",
                        help="auto=Langfuse if creds present, sqlite=force local")
    args = parser.parse_args()

    data, is_seeded = build_data(args.db, force_sqlite=(args.source == "sqlite"))
    plot(data, args.out, is_seeded)

    if is_seeded:
        print("NOTE: Fewer than 3 real version tags found — illustrative seed data used.")
    print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()
