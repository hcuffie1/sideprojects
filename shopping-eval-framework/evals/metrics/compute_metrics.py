"""
Deterministic metrics computed over a list of agent eval results.
No LLM calls — pure arithmetic over the state dicts returned by agent.invoke().

Usage:
    from evals.metrics.compute_metrics import compute_metrics
    metrics = compute_metrics(results)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agent.nodes.constraint_check_node import check_constraint  # noqa: E402


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
            "no_valid_results_rate": None,
            "oos_rate_top1": None,
            "n": 0,
        }

    top1_valid = 0
    constraints_total = 0
    constraints_satisfied = 0
    groundedness_scores = []
    no_results_count = 0
    oos_top1_count = 0

    for result in results:
        ranked = result.get("ranked_products", [])
        annotations = result.get("groundedness_annotations", [])
        query_spec = result.get("query_spec", {})
        hard_constraints = query_spec.get("hard_constraints", [])

        # no_valid_results_rate
        if not ranked:
            no_results_count += 1
            continue

        top1 = ranked[0]

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
        "no_valid_results_rate": no_results_count / n,
        "oos_rate_top1": (
            oos_top1_count / runs_with_results if runs_with_results else None
        ),
        "n": n,
    }
