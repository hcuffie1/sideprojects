"""
Deterministic metrics computed over a list of agent eval results.
No LLM calls — pure arithmetic over the state dicts returned by agent.invoke().

Exception: avg_citation_accuracy calls the spec_citation LLM evaluator if
citation scores are not already cached on the results.

Usage:
    from evals.metrics.compute_metrics import compute_metrics
    metrics = compute_metrics(results)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agent.nodes.constraint_check_node import check_constraint  # noqa: E402
from evals.metrics.spec_citation import citation_accuracy  # noqa: E402
from evals.metrics.ranking_metrics import compute_ranking_metrics  # noqa: E402


def _passes_hard_constraints(product: dict, constraints: list) -> bool:
    """Return True if the product satisfies every hard constraint."""
    return all(
        check_constraint(product, c)[0]
        for c in constraints
        if c.get("is_hard")
    )


def compute_metrics(results: list) -> dict:
    """
    Compute aggregate metrics over a list of agent result dicts.

    Each result is the state dict returned by agent.invoke(), optionally
    augmented with a 'query_spec' key containing the canonical query spec
    (needed for constraint-level assertions).

    Metrics:
      top1_valid_rate            % of runs where top-ranked product satisfies
                                 all hard constraints and is in stock
      constraint_satisfaction_rate  % of individual hard constraints satisfied
                                    by the top-ranked product
      avg_groundedness           mean groundedness score across all annotated
                                 products in all runs
      no_valid_results_rate      % of runs where ranked_products == []
      oos_rate_top1              % of runs where top-ranked product is
                                 out-of-stock (guardrail failure)
    """
    if not results:
        return {
            "top1_valid_rate": None,
            "constraint_satisfaction_rate": None,
            "avg_groundedness": None,
            "avg_citation_accuracy": None,
            "no_valid_results_rate": None,
            "oos_rate_top1": None,
            "avg_candidates_eliminated": None,
            "avg_output_violations": None,
            "avg_hit_rate_at_1": None,
            "avg_precision_at_k": None,
            "avg_recall_at_k": None,
            "avg_ndcg_at_k": None,
            "n": 0,
        }

    top1_valid = 0
    constraints_total = 0
    constraints_satisfied = 0
    groundedness_scores = []
    citation_scores = []
    no_results_count = 0
    oos_top1_count = 0
    candidates_eliminated_counts = []
    output_violations_counts = []

    for result in results:
        ranked = result.get("ranked_products", [])
        annotations = result.get("groundedness_annotations", [])
        query_spec = result.get("query_spec", {})
        hard_constraints = query_spec.get("hard_constraints", [])

        # candidates_eliminated — pipeline throughput (computed before early-exit)
        candidates_eliminated_counts.append(
            len(result.get("constraint_violations", []))
        )

        # no_valid_results_rate
        if not ranked:
            no_results_count += 1
            continue

        top1 = ranked[0]

        # output_violations — guardrail metric (should always be 0)
        hard = [c for c in hard_constraints if c.get("is_hard", True)]
        out_v = sum(
            1 for p in ranked
            if any(not check_constraint(p, c)[0] for c in hard)
        )
        output_violations_counts.append(out_v)

        # oos_rate_top1
        if not top1.get("in_stock"):
            oos_top1_count += 1

        # top1_valid_rate
        if top1.get("in_stock") and _passes_hard_constraints(
            top1, hard_constraints
        ):
            top1_valid += 1

        # constraint_satisfaction_rate
        for c in hard_constraints:
            if not c.get("is_hard", True):
                continue
            constraints_total += 1
            if check_constraint(top1, c)[0]:
                constraints_satisfied += 1

        # avg_groundedness
        for a in annotations:
            score = a.get("score")
            if score is not None:
                groundedness_scores.append(score)

        # avg_citation_accuracy — use cached score if present, else compute
        cached = result.get("citation_accuracy")
        if cached is not None:
            cit = cached
        else:
            cit = citation_accuracy(result)
        if cit.get("score") is not None:
            citation_scores.append(cit["score"])

    n = len(results)
    runs_with_results = n - no_results_count

    return {
        "top1_valid_rate": (
            top1_valid / runs_with_results if runs_with_results else None
        ),
        "constraint_satisfaction_rate": (
            constraints_satisfied / constraints_total
            if constraints_total else None
        ),
        "avg_groundedness": (
            sum(groundedness_scores) / len(groundedness_scores)
            if groundedness_scores else None
        ),
        "avg_citation_accuracy": (
            sum(citation_scores) / len(citation_scores)
            if citation_scores else None
        ),
        "no_valid_results_rate": no_results_count / n,
        "oos_rate_top1": (
            oos_top1_count / runs_with_results if runs_with_results else None
        ),
        "avg_candidates_eliminated": (
            sum(candidates_eliminated_counts) / len(candidates_eliminated_counts)
            if candidates_eliminated_counts else None
        ),
        "avg_output_violations": (
            sum(output_violations_counts) / len(output_violations_counts)
            if output_violations_counts else None
        ),
        **compute_ranking_metrics(results),
        "n": n,
    }
