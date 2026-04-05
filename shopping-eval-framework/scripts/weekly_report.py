"""
Weekly eval report — runs the full canonical query suite, computes metrics,
classifies failures, generates insights, and prints a formatted summary.

Usage:
    python scripts/weekly_report.py
"""
import sys
import os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from agent.graph import agent  # noqa: E402
from evals.canonical_queries import CANONICAL_QUERIES  # noqa: E402
from evals.metrics.compute_metrics import compute_metrics  # noqa: E402
from evals.metrics.failure_analysis import failure_distribution  # noqa: E402
from evals.insights.analyze_results import analyze  # noqa: E402

EMPTY_STATE = {
    "conversation_history": [],
    "query": "",
    "parsed_constraints": [],
    "category": None,
    "candidate_products": [],
    "filtered_products": [],
    "constraint_violations": [],
    "ranked_products": [],
    "groundedness_annotations": [],
    "final_response": "",
    "agent_rationale": "",
    "trace_id": None,
    "eval_scores": None,
}


def _run_query(q: dict) -> dict:
    if q.get("type") == "multi_turn":
        state = {**EMPTY_STATE}
        for turn in q["turns"]:
            state["query"] = turn["query"]
            state = agent.invoke(state)
        state["query_spec"] = q
        return state
    else:
        result = agent.invoke({**EMPTY_STATE, "query": q["query"]})
        result["query_spec"] = q
        return result


def _fmt(value) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def main():
    today = date.today().isoformat()
    n_queries = len(CANONICAL_QUERIES)

    print(f"\n{'='*50}")
    print("  Shopping Agent Weekly Eval Report")
    print(f"{'='*50}")
    print(f"  Date:    {today}")
    print(f"  Mode:    full")
    print(f"  Queries: {n_queries}")
    print(f"{'='*50}\n")

    results = []
    for q in CANONICAL_QUERIES:
        try:
            sys.stdout.write(f"  Running [{q['id']}]... ")
            sys.stdout.flush()
            result = _run_query(q)
            results.append(result)
            ranked = len(result.get("ranked_products", []))
            print(f"done ({ranked} ranked)")
        except Exception as e:
            print(f"ERROR: {e}")

    if not results:
        print("No results collected. Exiting.")
        return

    metrics = compute_metrics(results)
    failures = failure_distribution(results)
    insights = analyze(metrics, failures)

    print(f"\n{'─'*50}")
    print("METRICS")
    print(f"{'─'*50}")
    metric_labels = {
        "top1_valid_rate": "top1_valid_rate",
        "constraint_satisfaction_rate": "constraint_satisfaction_rate",
        "avg_groundedness": "avg_groundedness",
        "no_valid_results_rate": "no_valid_results_rate",
        "oos_rate_top1": "oos_rate_top1",
    }
    for key, label in metric_labels.items():
        print(f"  {label:<34} {_fmt(metrics.get(key))}")

    print(f"\n{'─'*50}")
    print("FAILURE DISTRIBUTION")
    print(f"{'─'*50}")
    for mode, count in sorted(
        failures.items(), key=lambda x: -x[1]
    ):
        bar = "█" * count
        print(f"  {mode:<30} {count:>3}  {bar}")

    print(f"\n{'─'*50}")
    print("INSIGHTS")
    print(f"{'─'*50}")
    status_icon = "✓" if insights["pass"] else "✗"
    print(f"  {status_icon} Threshold {'met' if insights['pass'] else 'NOT met'}")
    top = insights.get("top_failure_mode") or "none"
    print(f"  Top failure mode: {top}")
    for rec in insights.get("recommendations", []):
        print(f"  → {rec}")

    print(f"\n{'='*50}\n")


if __name__ == "__main__":
    main()
