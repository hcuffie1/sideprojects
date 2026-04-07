"""
Failure taxonomy for agent eval results.

Each result is classified into exactly one failure mode, checked in
priority order:

  out_of_stock_presented   top result has in_stock=False
  constraint_violation     top result violates a hard constraint
  hallucination            any groundedness score < 0.5
  missing_spec_failure     hard constraint violation reason is spec_missing
  impossible_constraints   ranked_products==[] AND satisfiable=False on query
  catalog_gap              ranked_products==[] AND satisfiable=True on query
                           (valid constraints, nothing in current catalog)
  no_results               ranked_products==[] unexpectedly (no expected flag)
  ranking_failure          valid products exist but top result is suboptimal
  success                  none of the above

The impossible_constraints / catalog_gap split requires the query_spec to
carry a `satisfiable` bool field (added in Phase 2.6). Queries without the
field default to catalog_gap, since unknown = assume real products exist.
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

    # 5-6. no ranked products
    if not ranked:
        if not expected_no_products:
            # Unexpected empty results — genuine failure
            return "no_results"
        # Expected empty results — classify by whether constraints were
        # physically satisfiable or just absent from the catalog
        satisfiable = query_spec.get("satisfiable", True)
        if not satisfiable:
            return "impossible_constraints"
        return "catalog_gap"

    # 7. ranking_failure — valid candidates existed but top result is poor
    filtered = result.get("filtered_products", [])
    if filtered:
        top_id = ranked[0].get("id")
        filtered_ids = {p.get("id") for p in filtered}
        if top_id not in filtered_ids:
            return "ranking_failure"

    return "success"


def failure_distribution(results: list) -> dict:
    """
    Count failure modes across a list of results.

    Returns a dict mapping each mode to its count, e.g.:
      {"success": 5, "catalog_gap": 2, "impossible_constraints": 1}
    """
    counts: dict = {}
    for result in results:
        mode = classify_failure(result)
        counts[mode] = counts.get(mode, 0) + 1
    return counts
