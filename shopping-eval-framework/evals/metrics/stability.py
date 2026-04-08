"""
Run-over-run variance statistics for the shopping agent.

Core functions used by both scripts/stability_test.py (CLI) and
scripts/run_evals.py (--stability flag).

run_stability_test(query_id, n=3) -> dict
    Runs a single canonical query N times and returns:
    {
      query_id, n_runs,
      metrics: {
        groundedness|constraint_satisfaction|top1_valid:
          {mean, std, cv}
      },
      product_set_stability: float,     # Jaccard across runs (1.0 = identical)
      failure_mode_consistency: bool,
      failure_modes_seen: [str, ...]
    }

print_stability_report(report) -> None
    Prints a formatted variance summary to stdout.
"""
import sys
import time
import statistics

from langfuse import observe, get_client

from agent.graph import agent
from agent.nodes.constraint_check_node import check_constraint
from evals.canonical_queries import CANONICAL_QUERIES
from evals.metrics.failure_analysis import classify_failure

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


# ── per-result metric extractors ──────────────────────────────────────────────

def _groundedness(result: dict) -> float:
    anns = result.get("groundedness_annotations", [])
    scores = [a["score"] for a in anns if "score" in a]
    return sum(scores) / len(scores) if scores else 0.0


def _constraint_satisfaction(result: dict) -> float:
    ranked = result.get("ranked_products", [])
    if not ranked:
        return 1.0
    query_spec = result.get("query_spec", {})
    hard = [
        c for c in query_spec.get("hard_constraints", [])
        if c.get("is_hard", True)
    ]
    if not hard:
        return 1.0
    violations = sum(
        1 for p in ranked
        if any(not check_constraint(p, c)[0] for c in hard)
    )
    return 1.0 - (violations / len(ranked))


def _top1_valid(result: dict) -> float:
    ranked = result.get("ranked_products", [])
    if not ranked:
        return 0.0
    top = ranked[0]
    if not top.get("in_stock"):
        return 0.0
    query_spec = result.get("query_spec", {})
    hard = [
        c for c in query_spec.get("hard_constraints", [])
        if c.get("is_hard", True)
    ]
    if any(not check_constraint(top, c)[0] for c in hard):
        return 0.0
    return 1.0


def _ranked_ids(result: dict) -> frozenset:
    return frozenset(p["id"] for p in result.get("ranked_products", []))


# ── aggregation helpers ───────────────────────────────────────────────────────

def _jaccard(sets: list) -> float:
    """Jaccard similarity across a list of frozensets."""
    if not sets:
        return 1.0
    intersection = sets[0].copy()
    union = sets[0].copy()
    for s in sets[1:]:
        intersection &= s
        union |= s
    return len(intersection) / len(union) if union else 1.0


def _metric_stats(values: list) -> dict:
    if not values:
        return {"mean": None, "std": None, "cv": None}
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    cv = std / mean if mean else 0.0
    return {"mean": round(mean, 4), "std": round(std, 4), "cv": round(cv, 4)}


# ── core runner ───────────────────────────────────────────────────────────────

@observe()
def _run_once(query_spec: dict, run_index: int, version: str = "v1") -> dict:
    get_client().update_current_span(
        name=f"stability-{query_spec['id']}-run{run_index}",
        input={"query": query_spec.get("query", "")},
        metadata={
            "query_id": query_spec["id"],
            "eval_type": "stability_test",
            "agent_version": version,
            "run_index": run_index,
            "tags": ["eval", "stability_test", version],
        },
    )
    last_exc = None
    for attempt in range(3):
        try:
            result = agent.invoke({**EMPTY_STATE, "query": query_spec["query"]})
            result["query_spec"] = query_spec
            get_client().update_current_span(
                output={"response": result.get("final_response", "")[:200]},
            )
            return result
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                wait = 15 * (attempt + 1)
                print(f" [transient error, retrying in {wait}s: {exc}]")
                time.sleep(wait)
    raise last_exc


def run_stability_test(query_id: str, n: int = 3, version: str = "v1") -> dict:
    """
    Run a single canonical query N times and return variance statistics.

    Only supports single-turn queries (multi-turn raises ValueError).
    Langfuse traces are tagged eval_type=stability_test for separate
    filtering from standard eval runs.
    """
    query_spec = next(
        (q for q in CANONICAL_QUERIES if q["id"] == query_id), None
    )
    if query_spec is None:
        raise ValueError(f"Unknown query ID: {query_id}")
    if query_spec.get("type") == "multi_turn":
        raise ValueError(
            f"{query_id} is a multi-turn query — "
            "stability test only supports single-turn queries."
        )

    print(
        f"\n  Running {n} iterations of [{query_id}]: "
        f"{query_spec.get('description', '')}"
    )
    results = []
    for i in range(1, n + 1):
        sys.stdout.write(f"    Run {i}/{n}... ")
        sys.stdout.flush()
        result = _run_once(query_spec, i, version)
        results.append(result)
        g = _groundedness(result)
        mode = classify_failure(result)
        print(f"groundedness={g:.3f}  failure_mode={mode}")

    groundedness_vals = [_groundedness(r) for r in results]
    constraint_vals = [_constraint_satisfaction(r) for r in results]
    top1_vals = [_top1_valid(r) for r in results]
    ranked_sets = [_ranked_ids(r) for r in results]
    failure_modes = [classify_failure(r) for r in results]

    return {
        "query_id": query_id,
        "n_runs": n,
        "metrics": {
            "groundedness": _metric_stats(groundedness_vals),
            "constraint_satisfaction": _metric_stats(constraint_vals),
            "top1_valid": _metric_stats(top1_vals),
        },
        "product_set_stability": round(_jaccard(ranked_sets), 4),
        "failure_mode_consistency": len(set(failure_modes)) == 1,
        "failure_modes_seen": failure_modes,
    }


# ── reporting ─────────────────────────────────────────────────────────────────

def print_stability_report(report: dict) -> None:
    qid = report["query_id"]
    n = report["n_runs"]
    print(f"\n{'─'*55}")
    print(f"STABILITY REPORT  [{qid}]  n={n}")
    print(f"{'─'*55}")
    for name, stats in report["metrics"].items():
        mean = f"{stats['mean']:.4f}" if stats["mean"] is not None else "N/A"
        std = f"±{stats['std']:.4f}" if stats["std"] is not None else ""
        cv_str = (
            f"  cv={stats['cv']:.3f}" if stats["cv"] is not None else ""
        )
        flag = "  ⚠ high variance" if (stats["cv"] or 0) > 0.1 else ""
        print(f"  {name:<28} {mean} {std}{cv_str}{flag}")

    stability = report["product_set_stability"]
    stab_flag = "  ⚠ unstable" if stability < 0.8 else ""
    print(f"  {'product_set_stability':<28} {stability:.4f}{stab_flag}")

    consistent = report["failure_mode_consistency"]
    modes = ", ".join(report["failure_modes_seen"])
    icon = "✓" if consistent else "✗  ⚠ inconsistent failure modes"
    print(f"  {'failure_mode_consistency':<28} {icon}  [{modes}]")
