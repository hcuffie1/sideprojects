"""
Failure taxonomy for agent eval results.

Each result is classified into exactly one failure mode, checked in
priority order:

  out_of_stock_presented   top result has in_stock=False
  constraint_violation     top result violates a hard constraint
  hallucination            any groundedness score < 0.5
  missing_spec_failure     hard constraint violation reason is spec_missing
  no_results               ranked_products==[] when results were expected
  ranking_failure          valid products exist but top result is suboptimal
  success                  none of the above
"""


def classify_failure(result: dict) -> str:
    """Return the failure mode label for a single agent result."""
    ranked = result.get("ranked_products", [])
    annotations = result.get("groundedness_annotations", [])
    violations = result.get("constraint_violations", [])
    query_spec = result.get("query_spec", {})
    expected_no_products = query_spec.get("expected_no_products_found", False)

    # 1. out_of_stock_presented
    if ranked and not ranked[0].get("in_stock"):
        return "out_of_stock_presented"

    # 2. constraint_violation (hard constraint, non-missing-spec)
    hard_violations = [
        v for v in violations
        if v.get("is_hard") and v.get("reason") != "spec_missing"
    ]
    if hard_violations:
        return "constraint_violation"

    # 3. hallucination
    if any(a.get("score", 1.0) < 0.5 for a in annotations):
        return "hallucination"

    # 4. missing_spec_failure
    missing_spec_violations = [
        v for v in violations
        if v.get("is_hard") and v.get("reason") == "spec_missing"
    ]
    if missing_spec_violations:
        return "missing_spec_failure"

    # 5. no_results (unexpected)
    if not ranked and not expected_no_products:
        return "no_results"

    # 6. ranking_failure — valid candidates existed but top result is poor
    # Heuristic: filtered_products has more items than ranked suggests were used
    filtered = result.get("filtered_products", [])
    if ranked and filtered:
        top_id = ranked[0].get("id")
        # If top result is not in filtered at all, something went wrong
        filtered_ids = {p.get("id") for p in filtered}
        if top_id not in filtered_ids:
            return "ranking_failure"

    return "success"


def failure_distribution(results: list) -> dict:
    """
    Count failure modes across a list of results.

    Returns a dict mapping each mode to its count, e.g.:
      {"success": 5, "missing_spec_failure": 1, ...}
    """
    counts: dict = {}
    for result in results:
        mode = classify_failure(result)
        counts[mode] = counts.get(mode, 0) + 1
    return counts
