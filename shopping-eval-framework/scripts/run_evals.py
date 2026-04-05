"""
Run the agent on canonical queries and print results.

Usage:
    python scripts/run_evals.py                  # default: full
    python scripts/run_evals.py --mode dev       # only q_001
    python scripts/run_evals.py --mode sample    # first 3 single-turn
    python scripts/run_evals.py --mode full      # all queries
    python scripts/run_evals.py q_001 q_003      # specific query IDs
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from agent.graph import agent  # noqa: E402
from evals.canonical_queries import CANONICAL_QUERIES  # noqa: E402
from evals.metrics.compute_metrics import compute_metrics  # noqa: E402
from evals.metrics.failure_analysis import failure_distribution  # noqa: E402

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


def run_single_query(query_spec: dict) -> dict:
    print(f"\n{'='*60}")
    print(f"[{query_spec['id']}] {query_spec['description']}")
    print(f"Query: {query_spec['query']}")
    print("-" * 60)

    result = agent.invoke({**EMPTY_STATE, "query": query_spec["query"]})

    print(f"Category detected: {result.get('category')}")
    print(
        f"Constraints parsed: {len(result.get('parsed_constraints', []))}"
    )
    print(
        f"Candidates retrieved: {len(result.get('candidate_products', []))}"
    )
    print(
        f"After constraint check: {len(result.get('filtered_products', []))}"
    )
    print(
        f"After ranking (top 5): {len(result.get('ranked_products', []))}"
    )
    print(f"Violations: {len(result.get('constraint_violations', []))}")
    print(f"\nRationale: {result.get('agent_rationale')}")
    print(f"\nResponse:\n{result.get('final_response')}")

    result["query_spec"] = query_spec
    return result


def run_multiturn_query(query_spec: dict) -> dict:
    print(f"\n{'='*60}")
    print(
        f"[{query_spec['id']}] {query_spec['description']} (multi-turn)"
    )
    print("-" * 60)

    state = {**EMPTY_STATE}
    for i, turn in enumerate(query_spec["turns"], 1):
        print(f"\n  Turn {i}: {turn['query']}")
        state["query"] = turn["query"]
        state = agent.invoke(state)
        print(f"  Category: {state.get('category')}")
        print(
            f"  Constraints: {len(state.get('parsed_constraints', []))}"
        )
        print(f"  Ranked: {len(state.get('ranked_products', []))}")

    print(f"\nFinal response:\n{state.get('final_response')}")
    state["query_spec"] = query_spec
    return state


def select_queries(mode: str, ids: list) -> list:
    single_turn = [
        q for q in CANONICAL_QUERIES if q.get("type") != "multi_turn"
    ]
    if ids:
        return [q for q in CANONICAL_QUERIES if q["id"] in ids]
    if mode == "dev":
        return [single_turn[0]]
    if mode == "sample":
        return single_turn[:3]
    return CANONICAL_QUERIES  # full


def print_metrics_summary(metrics: dict, failures: dict) -> None:
    print(f"\n{'='*60}")
    print("METRICS")
    for k, v in metrics.items():
        if k == "n":
            continue
        display = f"{v:.3f}" if isinstance(v, float) else str(v)
        print(f"  {k:<34} {display}")

    print("\nFAILURE DISTRIBUTION")
    for mode, count in sorted(failures.items()):
        print(f"  {mode:<30} {count}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["dev", "sample", "full"],
        default="full",
        help="dev=q_001 only, sample=first 3, full=all"
    )
    parser.add_argument(
        "query_ids",
        nargs="*",
        help="Optional specific query IDs to run"
    )
    args = parser.parse_args()

    queries = select_queries(args.mode, args.query_ids)
    results = []

    for q in queries:
        try:
            if q.get("type") == "multi_turn":
                result = run_multiturn_query(q)
            else:
                result = run_single_query(q)
            results.append(result)
        except Exception as e:
            print(f"ERROR on {q['id']}: {e}")

    if results:
        metrics = compute_metrics(results)
        failures = failure_distribution(results)
        print_metrics_summary(metrics, failures)
