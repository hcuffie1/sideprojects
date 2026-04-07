"""
Weekly eval report — runs the full canonical query suite, computes metrics,
classifies failures, generates insights, and prints a formatted summary.

Usage:
    python scripts/weekly_report.py
"""
import sys
import os
import uuid
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from langfuse import observe, get_client  # noqa: E402

from agent.graph import agent  # noqa: E402
from evals.canonical_queries import CANONICAL_QUERIES  # noqa: E402
from evals.metrics.compute_metrics import compute_metrics  # noqa: E402
from evals.metrics.failure_analysis import failure_distribution  # noqa: E402
from evals.insights.analyze_results import analyze  # noqa: E402
from evals.persistence import init_db, save_result  # noqa: E402
from evals.observability.drift_detector import (  # noqa: E402
    get_baseline_scores, detect_drift
)

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


@observe()
def _run_query(q: dict, run_id: str = "") -> dict:
    query_type = q.get("query_type", "unknown")
    turns = q.get("turns", [])
    query_text = q.get("query", turns[0]["query"] if turns else "")
    get_client().update_current_span(
        name=f"eval-{q['id']}",
        input={"query": query_text},
        metadata={
            "query_id": q["id"],
            "query_type": query_type,
            "tags": ["eval", "weekly_report", query_type],
            "description": q.get("description", ""),
            "run_id": run_id,
        },
    )

    if q.get("type") == "multi_turn":
        state = {**EMPTY_STATE}
        for turn in q["turns"]:
            state["query"] = turn["query"]
            state = agent.invoke(state)
        state["query_spec"] = q
        result = state
    else:
        result = agent.invoke({**EMPTY_STATE, "query": q["query"]})
        result["query_spec"] = q

    get_client().update_current_span(
        output={"response": result.get("final_response", "")[:200]},
    )
    result["_langfuse_trace_id"] = get_client().get_current_trace_id()
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
    run_id = str(uuid.uuid4())
    init_db()

    print(f"\n{'='*50}")
    print("  Shopping Agent Weekly Eval Report")
    print(f"{'='*50}")
    print(f"  Date:    {today}")
    print(f"  Mode:    full")
    print(f"  Queries: {n_queries}")
    print(f"  Run ID:  {run_id}")
    print(f"{'='*50}\n")

    results = []
    for q in CANONICAL_QUERIES:
        try:
            sys.stdout.write(f"  Running [{q['id']}]... ")
            sys.stdout.flush()
            result = _run_query(q, run_id)
            save_result(result, run_id)
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

    # Drift detection — compare current run to 7-day baseline in Langfuse
    _DRIFT_METRICS = [
        "groundedness", "constraint_satisfaction", "top1_valid",
        "output_violations",
    ]
    baseline = get_baseline_scores(_DRIFT_METRICS, days_back=7)
    current_scores = {
        "groundedness": metrics.get("avg_groundedness"),
        "constraint_satisfaction": metrics.get("constraint_satisfaction_rate"),
        "top1_valid": metrics.get("top1_valid_rate"),
        "output_violations": (
            sum(
                1 for r in results
                if r.get("output_violations", 0) > 0
            ) / len(results)
            if results else 0.0
        ),
    }
    drift_alerts = detect_drift(current_scores, baseline)

    print(f"\n{'─'*50}")
    print("DRIFT ALERTS")
    print(f"{'─'*50}")
    if not drift_alerts:
        print("  No drift detected (or no baseline available).")
    for alert in drift_alerts:
        icon = "[HIGH]" if alert["is_regression"] else "[INFO]"
        print(
            f"  {icon} {alert['metric']}: "
            f"{alert['baseline']:.3f} → {alert['current']:.3f} "
            f"({alert['relative_change']:+.1%})"
        )

    print(f"\n{'='*50}\n")
    get_client().flush()


if __name__ == "__main__":
    main()
