def score_product(product: dict, state: dict) -> float:
    """Simple scoring — extend with embeddings in later phases"""
    score = 0.0

    # Prefer products with more complete spec data
    spec_completeness = len(product.get("specs", {})) / 10.0
    score += spec_completeness

    # Soft constraint satisfaction bonus
    soft_constraints = [c for c in state.get("parsed_constraints", [])
                        if not c.get("is_hard")]
    for constraint in soft_constraints:
        field = constraint["field"]
        actual = product.get("specs", {}).get(field) or product.get(field)
        if actual is not None:
            score += 0.1  # bonus for having the field at all

    return score


def ranking_node(state: dict) -> dict:
    products = state.get("filtered_products", [])
    scored = [(p, score_product(p, state)) for p in products]
    scored.sort(key=lambda x: x[1], reverse=True)
    ranked = [p for p, _ in scored[:5]]

    return {
        **state,
        "ranked_products": ranked
    }
