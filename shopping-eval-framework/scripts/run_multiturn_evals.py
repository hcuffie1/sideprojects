"""
Run multi-turn canonical queries and report constraint retention per turn.

Usage:
    python scripts/run_multiturn_evals.py                  # all multi-turn queries
    python scripts/run_multiturn_evals.py --query q_024    # one query
    python scripts/run_multiturn_evals.py --version v3     # tag for Langfuse
"""
import sys
import os
import argparse
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from langfuse import observe, get_client  # noqa: E402

from agent.graph import agent  # noqa: E402
from evals.canonical_queries import CANONICAL_QUERIES  # noqa: E402
from evals.metrics.constraint_retention import (  # noqa: E402
    expected_constraints_at_turn, check_retention, retention_report
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
def run_query_with_retention(
    query_spec: dict, run_id: str = "", version: str = "v1"
) -> dict:
    """Run all turns of a multi-turn query and collect per-turn state for retention analysis."""
    turns = query_spec.get("turns", [])
    get_client().update_current_span(
        name=f"multiturn-{query_spec['id']}",
        input={"query": turns[0]["query"] if turns else ""},
        metadata={
            "query_id": query_spec["id"],
            "eval_type": "multiturn_eval",
            "agent_version": version,
            "run_id": run_id,
            "tags": ["eval", "multiturn_eval", version],
        },
    )

    print(f"\n{'='*60}")
    print(f"[{query_spec['id']}] {query_spec.get('description', '')} (multi-turn)")
    print("-" * 60)

    state = {**EMPTY_STATE}
    turn_states = []

    for i, turn in enumerate(turns, 1):
        print(f"\n  Turn {i}: {turn['query']}")
        state = {**state, "query": turn["query"]}
        state = agent.invoke(state)

        expected = expected_constraints_at_turn(turns, i - 1)
        parsed = state.get("parsed_constraints", [])
        retention = check_retention(parsed, expected)

        print(f"  Category:    {state.get('category')}")
        print(f"  Constraints: {[c['field'] for c in parsed]}")
        if expected:
            if retention["forgotten_fields"]:
                print(f"  ⚠ Forgotten: {retention['forgotten_fields']}")
            else:
                print(f"  ✓ Retention: all {len(expected)} expected fields present")

        turn_states.append(state)

    report = retention_report(turn_states, query_spec)

    print(f"\n  Ranked products: {len(state.get('ranked_products', []))}")
    print(f"  Final response:\n  {state.get('final_response', '')[:200]}")

    get_client().update_current_span(
        output={"response": state.get("final_response", "")[:200]},
        metadata={
            "overall_retention_rate": report["overall_retention_rate"],
            "any_forgetting": report["any_forgetting"],
            "final_ranked": len(state.get("ranked_products", [])),
        },
    )

    return {**state, "query_spec": query_spec, "retention_report": report}


def print_retention_summary(results: list) -> None:
    print(f"\n{'='*60}")
    print("CONSTRAINT RETENTION SUMMARY")
    print(f"{'='*60}")

    perfect = 0
    for r in results:
        rpt = r.get("retention_report", {})
        qid = rpt.get("query_id", "?")
        rate = rpt.get("overall_retention_rate", 1.0)
        flag = "✓" if not rpt.get("any_forgetting") else "⚠"
        print(f"  {flag} {qid:<10} retention={rate:.2f}", end="")
        turns = rpt.get("turns", [])
        forgotten_all = [
            f"T{t['turn_index']}:{t['forgotten_fields']}"
            for t in turns if t["forgotten_fields"]
        ]
        if forgotten_all:
            print(f"  forgotten={forgotten_all}", end="")
        print()
        if not rpt.get("any_forgetting"):
            perfect += 1

    total = len(results)
    print(f"\n  {perfect}/{total} queries had perfect retention across all turns")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", help="Run a single query by ID")
    parser.add_argument("--version", default="v1", help="Agent version tag for Langfuse")
    args = parser.parse_args()

    multiturn = [q for q in CANONICAL_QUERIES if q.get("type") == "multi_turn"]

    if args.query:
        multiturn = [q for q in multiturn if q["id"] == args.query]
        if not multiturn:
            print(f"No multi-turn query found with id '{args.query}'")
            sys.exit(1)

    print(f"Running {len(multiturn)} multi-turn queries (version={args.version})")

    run_id = str(uuid.uuid4())[:8]
    results = []
    for query_spec in multiturn:
        result = run_query_with_retention(query_spec, run_id=run_id, version=args.version)
        results.append(result)

    print_retention_summary(results)


if __name__ == "__main__":
    main()
