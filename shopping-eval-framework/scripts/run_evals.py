"""
Run the agent on canonical queries and print results.

Usage:
    python scripts/run_evals.py                  # default: full
    python scripts/run_evals.py --mode dev       # only q_001
    python scripts/run_evals.py --mode sample    # first 3 single-turn
    python scripts/run_evals.py --mode full      # all queries
    python scripts/run_evals.py q_001 q_003      # specific query IDs
    python scripts/run_evals.py --version v1_prime  # tag for A/A' comparison
"""
import sys
import os
import argparse
import uuid
import time

_MAX_RETRIES = 3
_RETRY_DELAYS = [2, 4]  # seconds between attempts 1→2, 2→3


def _invoke_with_retry(state: dict, query_id: str) -> dict:
    """Invoke the agent with up to _MAX_RETRIES attempts on transient errors."""
    last_exc = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return agent.invoke(state)
        except Exception as e:
            last_exc = e
            is_transient = "503" in str(e) or "UNAVAILABLE" in str(e)
            if is_transient and attempt < _MAX_RETRIES:
                delay = _RETRY_DELAYS[attempt - 1]
                print(
                    f"  [retry {attempt}/{_MAX_RETRIES - 1}] "
                    f"{query_id}: transient error, retrying in {delay}s — {e}"
                )
                time.sleep(delay)
            else:
                raise last_exc from None

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from langfuse import observe, get_client  # noqa: E402

from agent.graph import agent  # noqa: E402
from agent.nodes.constraint_check_node import check_constraint  # noqa: E402
from evals.canonical_queries import CANONICAL_QUERIES  # noqa: E402
from evals.metrics.compute_metrics import compute_metrics  # noqa: E402
from evals.metrics.failure_analysis import (  # noqa: E402
    failure_distribution, classify_failure
)
from evals.persistence import init_db, save_result  # noqa: E402
from evals.metrics.stability import (  # noqa: E402
    run_stability_test, print_stability_report
)
from evals.pricing import cost_for_tokens  # noqa: E402

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

def _compute_output_violations(result: dict) -> int:
    """Count ranked products that violate at least one hard constraint."""
    ranked = result.get("ranked_products", [])
    query_spec = result.get("query_spec", {})
    hard = [c for c in query_spec.get("hard_constraints", []) if c.get("is_hard", True)]
    if not hard:
        return 0
    return sum(
        1 for p in ranked
        if any(not check_constraint(p, c)[0] for c in hard)
    )


def _avg_groundedness(result: dict) -> float:
    annotations = result.get("groundedness_annotations", [])
    scores = [a["score"] for a in annotations if "score" in a]
    return sum(scores) / len(scores) if scores else 0.0


def _top1_valid(result: dict) -> float:
    ranked = result.get("ranked_products", [])
    if not ranked:
        return 0.0
    top = ranked[0]
    if not top.get("in_stock"):
        return 0.0
    query_spec = result.get("query_spec", {})
    hard = [c for c in query_spec.get("hard_constraints", []) if c.get("is_hard", True)]
    if any(not check_constraint(top, c)[0] for c in hard):
        return 0.0
    return 1.0


def _log_scores(result: dict) -> None:
    """Log eval scores to the current Langfuse trace via context."""
    ranked = result.get("ranked_products", [])
    avg_g = _avg_groundedness(result)
    out_v = _compute_output_violations(result)
    constraint_sat = 1.0 - (out_v / len(ranked)) if ranked else 1.0
    top1 = _top1_valid(result)

    candidates_eliminated = len(result.get("constraint_violations", []))

    for name, value, comment in [
        ("groundedness", avg_g,
         "Average groundedness score across ranked products"),
        ("constraint_satisfaction", constraint_sat,
         "% ranked products satisfying all hard constraints"),
        ("top1_valid", top1,
         "Binary: top result valid (in stock, no violations)"),
        ("output_violations", float(out_v),
         "Guardrail failures in final ranked output (target: 0)"),
        ("candidates_eliminated", float(candidates_eliminated),
         "Products filtered by constraint_check_node (pipeline throughput)"),
    ]:
        get_client().score_current_trace(
            name=name, value=value, comment=comment
        )

    if out_v > 0 or avg_g < 0.6:
        reason = "output_violations" if out_v > 0 else "low_groundedness"
        get_client().score_current_trace(
            name="needs_human_review",
            value=1.0,
            comment=f"Flagged: {reason}",
        )


@observe()
def run_single_query(
    query_spec: dict, run_id: str = "", version: str = "v1"
) -> dict:
    query_type = query_spec.get("query_type", "unknown")
    get_client().update_current_span(
        name=f"eval-{query_spec['id']}",
        input={"query": query_spec["query"]},
        metadata={
            "query_id": query_spec["id"],
            "query_type": query_type,
            "tags": ["eval", query_type, version],
            "description": query_spec.get("description", ""),
            "agent_version": version,
            "run_id": run_id,
        },
    )

    print(f"\n{'='*60}")
    print(f"[{query_spec['id']}] {query_spec['description']}")
    print(f"Query: {query_spec['query']}")
    print("-" * 60)

    t0 = time.perf_counter()
    result = _invoke_with_retry(
        {**EMPTY_STATE, "query": query_spec["query"]}, query_spec["id"]
    )
    latency_ms = (time.perf_counter() - t0) * 1000
    result["_latency_ms"] = latency_ms

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
    _log_scores(result)
    token_usage = result.get("_token_usage") or {}
    in_tok = token_usage.get("input_total", 0)
    out_tok = token_usage.get("output_total", 0)
    get_client().update_current_span(
        output={"response": result.get("final_response", "")[:200]},
        metadata={
            "failure_mode": classify_failure(result),
            "products_ranked": len(result.get("ranked_products", [])),
            "output_violations": _compute_output_violations(result),
            "tokens_input": in_tok,
            "tokens_output": out_tok,
            "latency_ms": round(latency_ms, 1),
            "cost_usd": round(cost_for_tokens(in_tok, out_tok), 6),
        },
    )
    result["_langfuse_trace_id"] = get_client().get_current_trace_id()
    return result


@observe()
def run_multiturn_query(
    query_spec: dict, run_id: str = "", version: str = "v1"
) -> dict:
    query_type = query_spec.get("query_type", "unknown")
    turns = query_spec.get("turns", [])
    get_client().update_current_span(
        name=f"eval-{query_spec['id']}",
        input={"query": turns[0]["query"] if turns else ""},
        metadata={
            "query_id": query_spec["id"],
            "query_type": query_type,
            "tags": ["eval", query_type, version],
            "description": query_spec.get("description", ""),
            "agent_version": version,
            "run_id": run_id,
        },
    )

    print(f"\n{'='*60}")
    print(
        f"[{query_spec['id']}] {query_spec['description']} (multi-turn)"
    )
    print("-" * 60)

    t0 = time.perf_counter()
    state = {**EMPTY_STATE}
    for i, turn in enumerate(turns, 1):
        print(f"\n  Turn {i}: {turn['query']}")
        state["query"] = turn["query"]
        state = agent.invoke(state)
        print(f"  Category: {state.get('category')}")
        print(
            f"  Constraints: {len(state.get('parsed_constraints', []))}"
        )
        print(f"  Ranked: {len(state.get('ranked_products', []))}")
    latency_ms = (time.perf_counter() - t0) * 1000
    state["_latency_ms"] = latency_ms

    print(f"\nFinal response:\n{state.get('final_response')}")
    state["query_spec"] = query_spec
    _log_scores(state)
    token_usage = state.get("_token_usage") or {}
    in_tok = token_usage.get("input_total", 0)
    out_tok = token_usage.get("output_total", 0)
    get_client().update_current_span(
        output={"response": state.get("final_response", "")[:200]},
        metadata={
            "failure_mode": classify_failure(state),
            "products_ranked": len(state.get("ranked_products", [])),
            "output_violations": _compute_output_violations(state),
            "tokens_input": in_tok,
            "tokens_output": out_tok,
            "latency_ms": round(latency_ms, 1),
            "cost_usd": round(cost_for_tokens(in_tok, out_tok), 6),
        },
    )
    state["_langfuse_trace_id"] = get_client().get_current_trace_id()
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
        "--version",
        default="v1",
        help="Agent version tag for A/A' comparison in Langfuse"
    )
    parser.add_argument(
        "query_ids",
        nargs="*",
        help="Optional specific query IDs to run"
    )
    parser.add_argument(
        "--stability",
        action="store_true",
        help="Run each single-turn canonical query 3x and report variance"
    )
    args = parser.parse_args()

    run_id = str(uuid.uuid4())
    init_db()

    if args.stability:
        single_turn = [
            q for q in CANONICAL_QUERIES if q.get("type") != "multi_turn"
        ]
        reports = []
        for q in single_turn:
            try:
                report = run_stability_test(q["id"], n=3)
                print_stability_report(report)
                reports.append(report)
            except Exception as e:
                print(f"ERROR on {q['id']}: {e}")
        print(f"\n{'='*60}")
        print(f"STABILITY SUMMARY  ({len(reports)} queries, n=3 each)")
        print(f"{'='*60}")
        high_variance = [
            r for r in reports
            if any(
                (s["cv"] or 0) > 0.1
                for s in r["metrics"].values()
            )
        ]
        inconsistent = [
            r for r in reports if not r["failure_mode_consistency"]
        ]
        print(f"  High-variance queries (CV > 0.1): {len(high_variance)}")
        for r in high_variance:
            print(f"    {r['query_id']}")
        print(f"  Inconsistent failure modes:       {len(inconsistent)}")
        for r in inconsistent:
            print(f"    {r['query_id']}  {r['failure_modes_seen']}")
        get_client().flush()
        sys.exit(0)

    queries = select_queries(args.mode, args.query_ids)
    results = []
    t_suite_start = time.perf_counter()

    for q in queries:
        try:
            if q.get("type") == "multi_turn":
                result = run_multiturn_query(q, run_id, args.version)
            else:
                result = run_single_query(q, run_id, args.version)
            save_result(result, run_id)
            results.append(result)
        except Exception as e:
            print(f"ERROR on {q['id']}: {e}")

    if results:
        metrics = compute_metrics(results)
        failures = failure_distribution(results)
        print_metrics_summary(metrics, failures)
        print(
            f"  Results saved to .eval_results/traces.db  (run_id: {run_id})"
        )
        if os.getenv("LANGFUSE_PUBLIC_KEY"):
            print(
                f"  Langfuse traces tagged: version={args.version}, "
                f"run_id={run_id}"
            )
        elapsed = time.perf_counter() - t_suite_start
        print(f"  Total elapsed: {elapsed:.1f}s ({len(results)} queries)")
        get_client().flush()
