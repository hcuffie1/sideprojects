from agent.tracing import traced_node

_DEFAULT_WEIGHTS = {
    "spec_completeness": 1.0,
    "soft_constraint_bonus": 0.1,
}


def score_product(product: dict, state: dict, config: dict | None = None) -> float:
    """
    Score a product for ranking. Accepts an optional config dict with keys:
      spec_completeness      — multiplier for spec field count / 10
      soft_constraint_bonus  — per-turn bonus for each matched soft constraint field
    Defaults match the historical baseline behaviour.
    """
    weights = {**_DEFAULT_WEIGHTS, **(config or {})}
    score = 0.0

    # Prefer products with more complete spec data
    spec_completeness = len(product.get("specs", {})) / 10.0
    score += spec_completeness * weights["spec_completeness"]

    # Soft constraint satisfaction bonus
    soft_constraints = [c for c in state.get("parsed_constraints", [])
                        if not c.get("is_hard")]
    for constraint in soft_constraints:
        field = constraint["field"]
        actual = product.get("specs", {}).get(field) or product.get(field)
        if actual is not None:
            score += weights["soft_constraint_bonus"]

    return score


@traced_node("RankingNode")
def ranking_node(state: dict, config: dict | None = None) -> dict:
    # Allow A/B runner to inject weights via state key without modifying the graph
    effective_config = config or state.get("_ranking_config")
    products = state.get("filtered_products", [])
    scored = [(p, score_product(p, state, effective_config)) for p in products]
    scored.sort(key=lambda x: x[1], reverse=True)
    ranked = [p for p, _ in scored[:5]]

    return {
        **state,
        "ranked_products": ranked
    }
